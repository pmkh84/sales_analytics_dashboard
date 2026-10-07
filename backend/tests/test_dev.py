"""Guard against silently using portable PostgreSQL after the Docker migration."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from sqlalchemy.engine import make_url

spec = spec_from_file_location("dashboard_dev", Path(__file__).resolve().parents[2] / "scripts/dev.py")
dev = module_from_spec(spec)
spec.loader.exec_module(dev)


@pytest.fixture
def compose_url(monkeypatch):
    values = {"POSTGRES_USER": "sales", "POSTGRES_PASSWORD": "test-only", "POSTGRES_DB": "sales_analytics"}
    monkeypatch.setattr(dev, "dotenv_values", lambda path: values)
    for key in values:
        monkeypatch.delenv(key, raising=False)
    return make_url("postgresql+psycopg://sales:test-only@127.0.0.1:5432/sales_analytics")


def test_start_requires_docker_even_when_a_local_database_is_listening(monkeypatch, compose_url):
    monkeypatch.setattr(dev, "listening", lambda *args: True)

    def no_docker():
        raise RuntimeError("Docker CLI not found")

    monkeypatch.setattr(dev, "find_docker", no_docker)
    with pytest.raises(RuntimeError, match="Docker CLI not found"):
        dev.start_database(compose_url)


def test_start_rejects_mismatched_compose_credentials_before_starting_docker(monkeypatch, compose_url):
    monkeypatch.setenv("POSTGRES_PASSWORD", "different-test-password")
    docker = MagicMock()
    monkeypatch.setattr(dev, "find_docker", docker)
    with pytest.raises(RuntimeError, match="same Compose database"):
        dev.start_database(compose_url)
    docker.assert_not_called()


def test_identity_check_rejects_connection_to_a_different_server(monkeypatch, compose_url):
    monkeypatch.setattr(dev, "docker_command", lambda docker, args: "container" if args[0] == "compose" else "111")
    engine = MagicMock()
    engine.connect.return_value.__enter__.return_value.scalar.return_value = "222"
    with pytest.raises(RuntimeError, match="different PostgreSQL server"):
        dev.verify_docker_database(engine, "docker", compose_url)


def test_identity_check_accepts_the_project_container(monkeypatch, compose_url):
    monkeypatch.setattr(dev, "docker_command", lambda docker, args: "container" if args[0] == "compose" else "111")
    engine = MagicMock()
    engine.connect.return_value.__enter__.return_value.scalar.return_value = "111"
    dev.verify_docker_database(engine, "docker", compose_url)
