# AI Sales Analytics Dashboard

**Clarity** is a sales analytics dashboard built for a two-day internship project. A standalone React frontend reads real PostgreSQL-backed analytics from a separate FastAPI application. OpenAI adds on-demand business insights and questions over compact, server-calculated aggregates.

## Features

- Revenue, orders, unique buying customers, average order value, and revenue growth.
- Daily revenue chart, category revenue shares, top products by revenue.
- Date ranges shared across analytics, paginated sales, and AI requests.
- Dashboard, Analytics, Sales, and AI Insights views; responsive mobile navigation.
- Loading skeletons, empty states, retries, and readable database/AI errors.
- 100 customers, 30 products, and 1,500 seeded transactions across seven months.
- No authentication or unnecessary infrastructure.

## Architecture

```text
React + TypeScript + Vite + Tailwind + Recharts
                   |
             REST / Axios
                   |
FastAPI routes -> analytics services -> SQLAlchemy -> PostgreSQL
                   |
          compact aggregate context
                   |
        isolated OpenAI Responses service
```

All metrics are calculated in SQL/Python. The frontend contains no fake API or hardcoded chart data. AI receives revenue summaries, category aggregates, top five products and monthly trends, never customer names/emails or individual sale records. AI has no SQL execution or database access.

## Folder structure

```text
frontend/
  src/
    components/   # Layout, charts, KPI cards, sales table, AI panel
    pages/
    services/     # Typed Axios calls
    hooks/
    types/
    utils/
    App.tsx
  .env.example
  package.json
backend/
  app/
    ai/           # OpenAI integration only
    models/
    schemas/
    routers/
    services/     # SQL analytics and period logic
    config.py
    database.py
    main.py
    seed.py
  tests/
  .env.example
  requirements.txt
  requirements-dev.txt
compose.yaml
render.yaml
.env.example      # Docker database settings only
```

## Prerequisites

- Python 3.12+
- Node.js 22.12+ (tested with Node 24)
- Docker Desktop running, or an existing PostgreSQL 17 database
- Optional OpenAI API key and access to the configured model

Commands below use **PowerShell** and start in the repository root. Do not overwrite existing `.env` files if already configured.

## Run on this Windows workspace

With Docker Desktop running and dependencies installed, run from the repository root:

```powershell
.\dev.cmd
```

Open **http://localhost:5173**. Keep the terminal open. Ctrl+C stops the API and UI;
the Docker database keeps running and its data persists in a named volume. To stop
the database separately, run `docker compose stop db`. After restarting Windows,
start Docker Desktop and run the same command again.

The launcher uses `backend/.env` regardless of the current directory and always
starts/reuses this project's Docker Compose PostgreSQL. It never starts portable
PostgreSQL or falls back to another server. It locates Docker Desktop's per-user or
system installation even when the terminal PATH has not refreshed. It validates
the Compose credentials, waits for a successful connection, and compares the
PostgreSQL cluster identifier with the actual Compose container. Only then does
it run the safe/idempotent seed, check the tables, start FastAPI, wait for API health,
and start Vite. An occupied API/UI port or invalid local URL stops startup with a
readable error. Backend changes require restarting this launcher; it runs FastAPI
without reload.

The launcher never resets passwords or an existing database. Its service logs are
in `.local/*.stdout.log` and `.local/*.stderr.log`. A read-only database check is:

```powershell
.\dev.cmd --check
```

The workspace's portable PostgreSQL was migrated to Docker. The current volume is
`sales_analytics_dashboard_sales_data_docker` for the default Compose project name.
The original `.local/pgdata`, old Docker volume `sales_analytics_dashboard_sales_data`,
and migration backup `.local/backups/portable-to-docker.dump` remain preserved.
Do not run portable PostgreSQL on port 5432 while using Docker. Do not use
`docker compose down -v` if you want to preserve the active database.

## 1. PostgreSQL setup

```powershell
Copy-Item .env.example .env
```

Edit root `.env`: choose a local database username, database name and password. Then:

```powershell
docker compose up -d db
docker compose ps
```

PostgreSQL listens only on `127.0.0.1:5432`. Its data persists in a Docker named volume. To stop it without removing data: `docker compose stop db`.

Compose uses `restart: unless-stopped`, so the database restarts when the Docker
engine starts unless you explicitly stopped the container. Docker Desktop itself
must also be running after a Windows restart.

Without Docker, create a PostgreSQL database and role using your provider or PostgreSQL tools, then supply its connection string in the backend environment. SQLite is deliberately unsupported.

## 2. Backend installation

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt
Copy-Item backend\.env.example backend\.env
```

Edit `backend/.env`:

| Variable | Meaning |
| --- | --- |
| `DATABASE_URL` | Required PostgreSQL connection string; match the credentials in root `.env`. |
| `FRONTEND_URL` | Exact allowed browser origin; locally `http://localhost:5173`. No path. |
| `OPENAI_API_KEY` | Optional, server only. Leave blank to use analytics without AI. |
| `OPENAI_MODEL` | Defaults to `gpt-4.1-mini`; select a Responses-compatible model available to your account. |

Example database URL format: `postgresql+psycopg://USER:PASSWORD@localhost:5432/DATABASE`.
Percent-encode reserved characters in username/password. Provider URLs starting with `postgres://` or `postgresql://` are normalized automatically. Preserve provider-required TLS query parameters (for example `?sslmode=require`).

Root `.env` is for Compose; backend reads **backend/.env** regardless of current directory. Environment variables override the file. Never commit secrets.

Optional Telegram sale notifications use backend-only `TELEGRAM_BOT_TOKEN`.
Any chat can subscribe with `/start` and unsubscribe with `/stop`; active
subscribers are stored in PostgreSQL. `TELEGRAM_CHAT_ID` is no longer used.
Missing bot credentials disable delivery with a startup warning;
`TELEGRAM_ENABLED=false` explicitly disables it. The API URL and timeout are also
configurable. See [Telegram integration](backend/TELEGRAM.md) for the event flows,
configuration, webhook setup, tests and delivery limitations.

The example files now use the same placeholder password. Replace it in both files
before initializing a new database. Changing `.env` after PostgreSQL has already
initialized its data directory/volume **does not change the stored role password**.
For an existing database, use its actual credentials, or deliberately update the
role password and then the connection settings. Never delete a volume/data directory
to fix a credential mismatch. The local development launcher uses Docker exclusively;
manual backend commands can still use an explicitly configured external PostgreSQL.

## 3. Initialize and seed

```powershell
cd backend
..\.venv\Scripts\python.exe -m app.seed
```

This creates the three tables, their relationships, constraints and indexes. It inserts deterministic demo entities with timestamps relative to the current date. Re-running against a database containing any customers/products/sales safely skips insertion; it never truncates existing data. Demo customer addresses use `example.com`.

The schema is initialized explicitly rather than during every request. This small project uses SQLAlchemy `create_all`; schema changes to an existing database need a deliberate migration. Rerunning the seed does not refresh timestamps in an old dataset.

## 4. Run the backend

From `backend/`:

```powershell
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

- API: http://localhost:8000
- Interactive API docs: http://localhost:8000/docs
- Health, database connection and required application tables: http://localhost:8000/api/health

## 5. Frontend installation and startup

Open a second terminal at the repository root:

```powershell
cd frontend
npm.cmd ci
Copy-Item .env.example .env
npm.cmd run dev
```

Open **http://localhost:5173** (use this exact origin to match CORS).
`frontend/.env` uses `VITE_API_URL=http://localhost:8000`. It must be the API origin, without `/api`. Only this public backend URL belongs in the frontend environment. Never put an API key in a `VITE_*` variable.

The dev server uses port 5173 strictly. If that port is occupied, stop the existing process or intentionally update the port and `FRONTEND_URL` together.

For macOS/Linux, use `python3 -m venv .venv`, `.venv/bin/python` (or `../.venv/bin/python` from backend), `cp` instead of `Copy-Item`, and `npm` instead of `npm.cmd`.

## Verification

At repository root:

```powershell
.\.venv\Scripts\python.exe -m ruff check backend
cd backend
..\.venv\Scripts\python.exe -m pytest -q
cd ../frontend
npm.cmd run build
```

Tests require reachable PostgreSQL and a database role allowed to create schemas. Each test creates a unique schema inside a transaction that is rolled back. Tests do not drop or overwrite your application tables.

Tests cover calculations and equal-length comparisons, UTC date boundaries, zero-filled chart buckets, empty data, pagination, input validation, allowed/blocked CORS, database failure sanitization, missing AI configuration, structured insight validation, and exclusion of customer details from model input. OpenAI is mocked in automated tests; no paid request is made.

`requirements-lock.txt` is a snapshot of the verified Python environment including development tools. Use it with Python 3.12 for a repeatable test environment. The smaller `requirements.txt` contains pinned direct production dependencies.

## API endpoints

All analytics and AI routes accept optional `start_date=YYYY-MM-DD` and `end_date=YYYY-MM-DD`. Default is the last 30 calendar days including today, in UTC. Both end-user dates are inclusive; database queries use an exclusive next-midnight upper bound.

| Method | Endpoint | Response / parameters |
| --- | --- | --- |
| GET | `/api/health` | Database connection and AI configuration status |
| GET | `/api/dashboard/summary` | Revenue, orders, buyers, AOV, growth, previous revenue, dates |
| GET | `/api/dashboard/revenue-trend` | `date`, `revenue`, `orders`; `interval=day\|month` |
| GET | `/api/dashboard/categories` | Category, revenue, orders, units |
| GET | `/api/dashboard/top-products` | Ranked by revenue; `limit=1..30`, default 5 |
| GET | `/api/sales/recent` | `items`, `total`, `limit`, `offset`; default 10, max 100 per page |
| GET | `/api/ai/insights` | `{"insights":[{"title":"...", "detail":"..."}]}` |
| POST | `/api/ai/ask` | Body `{"question":"Which category performs best?"}`; returns `{"answer":"..."}` |

Question length is 3–1,000 characters; blank questions are rejected. Date ranges are limited to 731 days. Expected failures use a consistent `{"detail":"..."}` response. FastAPI validation failures use its standard 422 detail list.

### Metric definitions

- **Revenue:** sum of recorded `total_amount`, in USD. Discounts are already reflected; this is not profit.
- **Order:** one Sale row (one product with a quantity). No separate cart/multi-line order model.
- **Customers:** distinct customers who purchased in the selected range, not lifetime registrations.
- **Average order value:** revenue divided by orders; zero with no orders.
- **Growth:** percentage change against the immediately preceding equal-length date range. Null means the prior revenue was zero; no misleading infinity/100% is invented.
- **Trend:** daily/monthly buckets, zero-filled for missing dates; partial months contain only selected dates.
- **AI:** observes the selected date range. Questions about unavailable periods or causal drivers must acknowledge missing data. Prompts discourage fabricated claims but model factuality is not guaranteed.

## AI setup

Set `OPENAI_API_KEY` in `backend/.env`, restart the backend, then click **Generate AI Insights** or submit a question. No OpenAI call happens on page load. Requests have a timeout, a bounded output budget, and no SDK retries. Insights use a JSON schema validated with Pydantic. Responses are rendered as text.

Without a key, both AI endpoints return a clear 503 setup message and the dashboard continues working. Provider throttling returns 429, connection/timeouts return 504, and invalid/upstream responses return 502. Live AI verification requires your own configured key; mocked tests do not prove account/model access.

This is intentionally an unauthenticated demo. Use seeded demonstration data when publishing. CORS is a browser policy, not access control: a public AI endpoint can be called outside your UI and incur usage charges. Configure provider spending controls for a public demo.

The integration follows the [official OpenAI Python Responses API documentation](https://developers.openai.com/api/reference/python).

## Deployment: Render + managed PostgreSQL

1. Push this repository to your own Git provider.
2. Create a managed PostgreSQL database. For Render, place the database and backend in the same region and use its internal URL when available.
3. Create a Render Python web service with **Root Directory = backend**.
4. Build command: `pip install -r requirements.txt`.
5. Start command: `python -m app.seed && uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
6. Set `DATABASE_URL`, `FRONTEND_URL`, optional `OPENAI_API_KEY`, and `OPENAI_MODEL` in Render's environment settings. Set Python to 3.12 using `PYTHON_VERSION`.
7. Set health check path to `/api/health`.
8. Open `https://YOUR-BACKEND.onrender.com/docs` and check `/api/health`.

The included `render.yaml` expresses the backend settings with secret values supplied in Render. The start command seeds only an empty database, so subsequent deploys preserve data. To use an existing non-demo database, initialize its schema deliberately and remove `python -m app.seed &&` from the start command.

See [Render's FastAPI deployment guide](https://render.com/docs/deploy-fastapi).

## Deployment: Vercel

1. Import the same repository as a Vercel project.
2. Select **Root Directory = frontend**, framework **Vite**.
3. Install: `npm ci`; build: `npm run build`; output: `dist`.
4. Set `VITE_API_URL=https://YOUR-BACKEND.onrender.com`.
5. Deploy. Set the backend's `FRONTEND_URL` to the exact resulting production frontend origin (no trailing path).
6. Restart/redeploy the backend after changing its environment. Rebuild/redeploy the frontend whenever `VITE_API_URL` changes.
7. Verify charts, pagination, AI behavior, and cross-origin API requests on the public URL.

Navigation uses local React state, so no SPA rewrite is required. Only the configured origin is allowed; a different Vercel preview hostname needs an intentional `FRONTEND_URL` change.

See [Vite on Vercel](https://vercel.com/docs/frameworks/frontend/vite). Hosting resources are not provisioned automatically by this repository.

## Troubleshooting

- **Database connection unavailable:** start PostgreSQL first, preferably with `.\dev.cmd`. Starting FastAPI and Vite alone does not start the database.
- **Database authentication failed:** `backend/.env` must match the password stored in PostgreSQL. Editing root `.env` or an example file cannot update an existing role password.
- **Database schema is not initialized:** connect to the intended database and run `python -m app.seed` from `backend/`. Health now detects missing application tables, even when `SELECT 1` would succeed.
- **Cannot reach server:** start FastAPI; verify `VITE_API_URL` and exact CORS origin. On Windows, use the documented localhost browser URL.
- **Empty dashboard:** choose the wider period, or seed an empty database. Old seeded dates do not automatically move forward.
- **AI not configured:** set the key on the backend only and restart it.
- **AI request failed:** check model access, API key and provider limits. Credentials are never included in API error responses.
- **PowerShell blocks npm.ps1:** use `npm.cmd` as shown.
- **No python command:** install Python 3.12+ and reopen your terminal. This workspace also has a pre-created `.venv` that can be used directly.

