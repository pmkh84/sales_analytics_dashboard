"""Run Docker Compose PostgreSQL, API and UI in order; preserve existing data."""

import argparse
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import dotenv_values
from pydantic import ValidationError
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

LOCAL = ROOT / ".local"
LOCAL_HOSTS = {"localhost", "127.0.0.1"}
CREATE_FLAGS = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0


def listening(host, port):
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


def database_problem(error):
    # Inspect locally, but never print driver exceptions (they can contain secrets).
    message = str(error.orig).lower()
    if "password authentication failed" in message:
        return "PostgreSQL rejected the password in backend/.env. Fix the existing role's credentials."
    if "does not exist" in message and "database" in message:
        return "The configured database does not exist. Create it in the existing PostgreSQL server."
    return "PostgreSQL is unreachable or rejected the connection. Check backend/.env and database logs."


def probe(engine, schema=False):
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
        if schema:
            tables = connection.execute(
                text("SELECT to_regclass('customers'), to_regclass('products'), to_regclass('sales')")
            ).one()
            if any(table is None for table in tables):
                raise RuntimeError("Database schema is missing. Run python -m app.seed from backend/.")


def spawn(command, cwd, label, handles, children, env=None):
    stdout = (LOCAL / f"{label}.stdout.log").open("a", encoding="utf-8")
    stderr = (LOCAL / f"{label}.stderr.log").open("a", encoding="utf-8")
    handles.extend([stdout, stderr])
    process = subprocess.Popen(
        command, cwd=cwd, stdout=stdout, stderr=stderr, env=env, creationflags=CREATE_FLAGS
    )
    children.append(process)
    return process


def find_docker():
    docker = shutil.which("docker")
    if docker:
        return docker
    # Docker Desktop can be installed per user before the terminal PATH is refreshed.
    candidates = [
        Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local")))
        / "Programs/DockerDesktop/resources/bin/docker.exe",
        Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Docker/Docker/resources/bin/docker.exe",
    ]
    for candidate in candidates:
        try:
            if candidate.is_file():
                return str(candidate)
        except OSError:
            continue
    raise RuntimeError("Docker CLI not found. Install Docker Desktop and reopen your terminal.")


def docker_command(docker, arguments, timeout=30):
    result = subprocess.run(
        [docker, *arguments], cwd=ROOT, capture_output=True, text=True,
        check=False, timeout=timeout, creationflags=CREATE_FLAGS,
    )
    if result.returncode:
        raise RuntimeError(
            "Docker command failed. Check Docker Desktop, port 5432, and docker compose logs db. "
            "The portable PostgreSQL must be stopped."
        )
    return result.stdout.strip()


def validate_compose_url(url):
    compose = dotenv_values(ROOT / ".env")
    if (
        url.host not in LOCAL_HOSTS
        or (url.port or 5432) != 5432
        or url.username != os.environ.get("POSTGRES_USER", compose.get("POSTGRES_USER"))
        or url.password != os.environ.get("POSTGRES_PASSWORD", compose.get("POSTGRES_PASSWORD"))
        or url.database != os.environ.get("POSTGRES_DB", compose.get("POSTGRES_DB"))
    ):
        raise RuntimeError("Root .env and backend/.env must describe the same Compose database.")


def start_database(url):
    validate_compose_url(url)
    docker = find_docker()
    docker_command(docker, ["info", "--format", "{{.ServerVersion}}"])
    print("Starting Docker Compose PostgreSQL...", flush=True)
    docker_command(docker, ["compose", "up", "-d", "db"], timeout=120)
    return docker


def verify_docker_database(engine, docker, url):
    container = docker_command(docker, ["compose", "ps", "--status", "running", "-q", "db"])
    if not container:
        raise RuntimeError("The project's Docker PostgreSQL container is not running.")
    query = "SELECT system_identifier::text FROM pg_control_system()"
    expected = docker_command(
        docker, ["exec", container, "psql", "-U", url.username, "-d", url.database, "-Atc", query]
    )
    with engine.connect() as connection:
        actual = connection.scalar(text(query))
    if actual != expected:
        raise RuntimeError(
            "DATABASE_URL reaches a different PostgreSQL server. Stop portable PostgreSQL on port 5432."
        )
    print("Verified: DATABASE_URL connects to this project's Docker PostgreSQL.", flush=True)


def wait_database(engine):
    deadline = time.monotonic() + 45
    while True:
        try:
            probe(engine)
            return
        except SQLAlchemyError as error:
            if time.monotonic() >= deadline or "password authentication failed" in str(error.orig).lower():
                raise RuntimeError(database_problem(error)) from None
        time.sleep(0.5)


def wait_http(url, process, label):
    import json
    from urllib.error import URLError
    from urllib.request import urlopen

    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"{label} exited. See .local/{label}.stderr.log.")
        try:
            with urlopen(url, timeout=2) as response:
                if label == "backend" and json.load(response).get("database") != "connected":
                    raise RuntimeError("API database health check failed.")
                return
        except (URLError, TimeoutError):
            time.sleep(0.5)
    raise RuntimeError(f"{label} did not become ready. See .local/{label}.stderr.log.")


def run(check=False):
    from app.config import get_settings

    settings = get_settings()
    url = make_url(settings.database_url)
    engine = create_engine(settings.database_url, connect_args={"connect_timeout": 3})
    handles, children = [], []
    try:
        if check:
            validate_compose_url(url)
            probe(engine, schema=True)
            verify_docker_database(engine, find_docker(), url)
            print("Database connection and all three application tables are ready.")
            return
        origin = urlsplit(settings.frontend_url)
        if origin.hostname not in LOCAL_HOSTS or origin.scheme != "http" or origin.port != 5173:
            raise RuntimeError("For local development set FRONTEND_URL to http://localhost:5173.")
        node = shutil.which("node")
        vite = ROOT / "frontend" / "node_modules" / "vite" / "bin" / "vite.js"
        if not node or not vite.exists():
            raise RuntimeError("Install Node.js and run npm.cmd ci inside frontend/ first.")
        frontend_env = {**dotenv_values(ROOT / "frontend" / ".env"), **os.environ}
        api_url = urlsplit(frontend_env.get("VITE_API_URL") or "http://localhost:8000")
        if (
            api_url.scheme != "http" or api_url.hostname not in LOCAL_HOSTS or api_url.port != 8000
            or api_url.path not in {"", "/"} or api_url.query or api_url.fragment
        ):
            raise RuntimeError("For local development set VITE_API_URL to http://localhost:8000.")
        for port in (8000, 5173):
            if listening("127.0.0.1", port):
                raise RuntimeError(f"Port {port} is occupied. Stop the earlier app before running dev.cmd.")
        LOCAL.mkdir(exist_ok=True)
        docker = start_database(url)
        wait_database(engine)
        verify_docker_database(engine, docker, url)
        print("Database connected. Checking schema and demo data...", flush=True)
        # Existing seed is idempotent and never overwrites existing application rows.
        result = subprocess.run(
            [sys.executable, "-m", "app.seed"], cwd=ROOT / "backend", capture_output=True,
            text=True, timeout=60, check=False, creationflags=CREATE_FLAGS,
        )
        if result.returncode:
            raise RuntimeError("Schema initialization failed. Check database permissions; data was not reset.")
        print(result.stdout.strip(), flush=True)
        probe(engine, schema=True)
        backend = spawn(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
            ROOT / "backend", "backend", handles, children,
        )
        wait_http("http://127.0.0.1:8000/api/health", backend, "backend")
        frontend = spawn(
            [node, str(vite), "--host", "127.0.0.1"], ROOT / "frontend", "frontend", handles, children,
        )
        wait_http("http://127.0.0.1:5173", frontend, "frontend")
        print(f"Ready: {settings.frontend_url}\nAPI: http://localhost:8000/docs\n"
              "Logs: .local/*.log. Ctrl+C stops API/UI; Docker PostgreSQL keeps running.", flush=True)
        while True:
            if any(child.poll() is not None for child in children):
                raise RuntimeError("A service exited. Check .local/*.stderr.log.")
            time.sleep(1)
    finally:
        # PostgreSQL is managed by Compose; only stop this launcher's API/UI children.
        for child in reversed(children):
            if child.poll() is None:
                child.terminate()
                child.wait(timeout=15)
        for handle in handles:
            handle.close()
        engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Read-only database connection/schema check")
    args = parser.parse_args()
    try:
        run(check=args.check)
    except KeyboardInterrupt:
        print("Stopped. PostgreSQL data has been preserved.")
    except ValidationError:
        print("Startup failed: invalid backend configuration. Check backend/.env.", file=sys.stderr)
        sys.exit(1)
    except SQLAlchemyError as error:
        print(f"Startup failed: {database_problem(error)}", file=sys.stderr)
        sys.exit(1)
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as error:
        print(f"Startup failed: {error}", file=sys.stderr)
        sys.exit(1)
