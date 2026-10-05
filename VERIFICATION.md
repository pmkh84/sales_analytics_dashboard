# Verification — 2026-10-05

## Passed

- PostgreSQL 17 Docker container started and reported healthy.
- Seed inserted 100 customers, 30 products and 1,500 sales spanning seven months.
- Second seed run skipped without changing existing data.
- `python -m pytest -q`: **15 passed** against PostgreSQL, with isolated transactional test schemas.
- `python -m ruff check backend`: passed.
- `python -m pip check`: no broken requirements.
- `npm run build`: TypeScript and Vite production build passed; chart bundle split removed the initial size warning.
- `npm install`: dependency audit reported no vulnerabilities at install time.
- Live `GET /api/health`: database connected, AI not configured.
- Browser rendered real backend KPIs, all three charts, and recent sales.
- Sales pagination moved from rows 1–8 to 9–16.
- 90-day filtering changed the count from 250 to 777 orders and reset pagination.
- Generate Insights and Ask AI displayed the missing-key message correctly.
- Backend shutdown produced a readable network error and retry control.
- Desktop (1440px) and mobile (390px) layouts inspected.
- Git ignores local environment files, virtual environment, dependencies and build outputs.

## Limits

- OpenAI success paths are tested with mocked SDK responses. No live paid request was made; configure `OPENAI_API_KEY` and verify model access before demonstrating AI output.
- Vercel/Render configuration and instructions are included; no remote resources were provisioned or deployment tested.
- TestClient emits a third-party Starlette deprecation warning about its httpx adapter. Tests pass; this is not an application failure.
- Data is generated demo data stored in PostgreSQL, not connected to an external sales system.

