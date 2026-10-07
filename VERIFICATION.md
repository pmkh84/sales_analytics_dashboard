# Verification

## USD/Toman dashboard display — 2026-10-07

- Full backend suite: **217 passed**, including **42 exchange-rate cases** with
  mocked external HTTP. Parsing, IRR/IRT normalization, cache expiry/concurrency,
  stale fallback/recovery, invalid responses, safe errors/logging and endpoint
  shape are covered. Existing business and Telegram tests continue to pass.
- TypeScript type checking and Vite production build passed. Backend/script Ruff,
  feature formatting and whitespace checks passed.
- React rendering checked loading, success, stale and unavailable card states,
  thousands separators, Persian currency label and provider timestamp in Tehran time.
  No browser was available through the browser tool; visual desktop/mobile checks
  and real browser interaction remain manual.
- Temporary Uvicorn startup on port 18001 passed: OpenAPI registration, live
  database health and missing-key HTTP 503. Telegram delivery and provider access
  were disabled for this check; the verification server was stopped afterward.
- No authenticated live provider call was made. Navasan requires a key and its
  trial quota/update frequency may require a longer TTL or suitable paid plan.
- In-process cache defaults to two minutes. Failed refreshes retain the provider
  timestamp and mark the previous quote stale; failures without cache stay isolated
  from analytics. Restart clears cache; multiple processes have separate caches.
- Business models, pricing calculations, Telegram code and sales UI/formatting
  remain unchanged. Local environment files were not modified; the new example
  credential is blank. No dependency, Redis, worker or migration was added.
- [Architecture, complete file inventory, commands and limitations](backend/EXCHANGE_RATE.md).

## Open Telegram subscriptions — 2026-10-07

- Full suite: **175 passed**; standalone notification unit suite: **43 passed**.
  All bot HTTP calls and webhook registration were mocked.
- `/start` accepts every chat, registers/reactivates it and updates available
  metadata. `/stop` deactivates it. Confirmations follow successful commits;
  failures do not undo subscription state. No invitation/authentication/approval
  logic or webhook secret was added.
- Sale events broadcast only to current active subscribers. Failures are isolated
  per recipient; subscriber lookup failure preserves successful sale responses.
- Subscriber table initialized in the configured demo database; existing business
  counts preserved. Existing seed/launcher handles initialization for future runs.
- Backend/launcher Ruff, notification-file formatting, dependency and whitespace
  checks passed. Temporary backend startup, database health, open webhook and
  registration CLI help passed. No real webhook was registered.
- Credentials found in the tracked environment example were replaced by empty
  placeholders. Local .env files were not modified. `TELEGRAM_CHAT_ID` is ignored.
- [Setup and architecture](backend/TELEGRAM.md).

## Docker database migration — 2026-10-07

- Docker Desktop is running using the `desktop-linux` context. The launcher now
  uses Docker Compose exclusively and finds per-user/system Docker installations
  even when the terminal PATH has not refreshed. No portable PostgreSQL fallback.
- Backed up the latest portable database to `.local/backups/portable-to-docker.dump`
  and restored it transactionally into a fresh Compose volume. Preserved the
  portable data directory and previous Docker volume.
- Active container: `sales_analytics_dashboard-db-1`, PostgreSQL 17, healthy,
  `127.0.0.1:5432`, restart policy `unless-stopped`.
- Active volume: `sales_analytics_dashboard_sales_data_docker`. Previous volume
  `sales_analytics_dashboard_sales_data` remains intact.
- Verified every source/target row using ordered row-content digests in UTC and
  preserved all sequence values. Latest source counts: **100 customers / 30 products
  / 1,499 sales**; this reflects the current data, without reseeding deleted sales.
- Launcher compares the PostgreSQL cluster identifier reached by `DATABASE_URL`
  against the Compose container, preventing connection to another local server.
- PostgreSQL tests against Docker: **66 passed**. Backend and launcher Ruff passed.
  Frontend code/dependencies were unchanged; its existing production build was
  already verified during startup recovery.
- Live API health, all seven data endpoints, frontend HTTP, and allowed-origin CORS
  passed. Restarted only the Docker database while API/UI were running; the API
  recovered, exact row contents and sequences persisted, and UI remained available.
- `dev.cmd --check` confirms Docker identity, database connectivity and schema.
  Ctrl+C stops API/UI; Compose keeps PostgreSQL running. Docker Desktop must be
  running after a Windows restart. No OS reboot was performed in this verification.

## Windows startup recovery — 2026-10-07

- Reproduced frontend HTTP 200 with API health/dashboard 503 while PostgreSQL was
  not listening. Portable PostgreSQL also failed with missing Visual C++ runtime
  DLLs; after repairing these, the configured database password was rejected.
- Repaired the local runtime using Microsoft-signed DLLs, recovered only the local
  role password, and synchronized ignored root/backend environment files. Kept the
  existing data directory, SCRAM authentication and all application records.
- Added `dev.cmd` / `scripts/dev.py`: database readiness, idempotent seed, API health,
  then UI startup; safe process ownership and orderly local database shutdown.
- Health now checks all three required tables. Database failures return specific,
  sanitized messages for authentication, missing database/schema and connectivity.
- PostgreSQL integration tests: **62 passed**. Backend/launcher Ruff, `pip check`
  and TypeScript/Vite production build passed.
- All eight read API routes and allowed-origin CORS verified against live services.
- Stopped all three services, verified their ports closed, and restarted successfully
  from `frontend/`. Database counts stayed **100 customers / 30 products / 1,500 sales**.
- Offline `dev.cmd --check` failed clearly; online check passed. No actual OS reboot
  was performed. No browser was available for visual verification; AI was mocked,
  with the live missing-key path verified separately.
- Full Persian diagnosis and run instructions: [DIAGNOSIS.fa.md](DIAGNOSIS.fa.md).

## Previous verification — 2026-10-05

## Edit Sale feature

- PostgreSQL integration suite: **54 passed**. Edit tests verify persisted changes to
  customer/product/quantity, current-price decimal totals, unchanged ID/date/order
  count, refreshed analytics, duplicate-name IDs, 404s, input validation, forbidden
  client totals, numeric overflow, rollback, and PATCH CORS.
- Ruff and TypeScript/Vite production build passed. Uvicorn startup passed on port
  8001. No browser is connected; visual interaction checks remain manual.
- `PATCH /api/sales/{sale_id}` requires all three fields (`customer_id`, `product_id`,
  `quantity`) using the existing request validation and returns the existing sale
  response shape with HTTP 200. Recent sales now also include customer/product IDs.
- Add and Edit share `SaleForm.tsx` (formerly `AddSaleForm.tsx`). Save closes/reset
  state and invokes `onSalesChanged`, incrementing revision and refetching sales,
  KPIs, and charts without a full browser reload. No migration is required.

### Manual Edit Sale test

1. Start backend/frontend using the README commands. Open `http://localhost:5173`
   and select Last 30 days. Add a disposable sale. Note its ID, amount, quantity,
   total revenue, and total orders.
2. Click **Edit** on its row. Verify the title identifies the sale and the customer,
   product, and quantity match that row. Cancel, then reopen; original values remain.
3. Change customer and product. Note the new unit price. Try blank quantity, 0,
   -1, and 1.5: saving must be blocked. Clear either dropdown: saving must be blocked.
4. Select both options, enter quantity 3, and save. With browser network throttling,
   verify “Saving…” and disabled controls. Expect PATCH with only the three editable
   fields, HTTP 200, and the modal closing after success.
5. Verify the row keeps its ID/date but shows the new customer/product, quantity 3,
   and amount equal to the new unit price times 3. Total orders stays constant;
   total revenue changes by new amount minus old amount. Check revenue, category,
   and top-product charts refetch (ranking may change). Reload to verify persistence.
6. Repeat from the Sales page, including a later page. On success the existing
   revision flow returns the list to page 1. Reopen Edit to verify saved values.
7. In `http://localhost:8000/docs`, PATCH a missing/deleted sale ID with valid
   customer/product IDs and quantity 1: expect 404. With an existing sale, try
   nonexistent customer/product IDs: expect 404. Try quantity 0 or an extra
   `total_amount`: expect 422 and the stored sale remains unchanged.
8. Open Edit, wait for options, then stop the backend and save. Verify an error,
   preserved form inputs, and re-enabled controls. Restart the backend and retry.
9. Smoke-test Add and Delete to confirm the shared form and refresh still work.

## Delete Sale feature

- PostgreSQL integration suite: **37 passed**. Delete coverage verifies 204 with no
  body, persisted removal, preserved customer/product records, repeat/missing ID 404,
  invalid ID 422, rollback after commit failure, DELETE CORS, and updated sales,
  orders, revenue, revenue trend, category totals, and top products.
- Ruff and TypeScript/Vite production build passed. Uvicorn startup, live database
  health, and the DELETE endpoint's OpenAPI registration passed on port 8001.
- No models or schemas added. Both create and delete call `onSalesChanged`, which
  increments App's existing revision. This refetches analytics and remounts/refetches
  the sales table at its first page without a browser reload.
- No browser is connected in this session; visual interaction checks remain manual.

### Manual Delete Sale test

1. Start the backend and frontend with the README commands. Open
   `http://localhost:5173`, select Last 30 days, and add a disposable sale with
   quantity 2. Record its displayed order ID and amount, total orders, and revenue.
2. Click that row's **Delete** button. Check the confirmation identifies the correct
   order. Click Cancel: the row and totals must remain unchanged.
3. Click Delete again and confirm. Expect `DELETE /api/sales/{id}` with 204 and an
   empty body in browser Network tools. With network throttling, verify delete
   buttons are disabled and the selected action reads “Deleting…” while pending.
4. Verify the row disappears, total orders falls by 1, revenue falls by the recorded
   amount, and revenue/category/product charts refetch. Reload to check persistence.
5. In browser DevTools Console, repeat the deleted ID's request:
   `fetch('http://localhost:8000/api/sales/ID', {method: 'DELETE'}).then(async r => console.log(r.status, await r.text()))`
   Replace ID with the deleted order ID. Expect 404 and “Sale not found.”
6. On the Sales page, delete a disposable sale from a later page. Verify the list
   returns to page 1; navigate to Dashboard and check refreshed KPIs/charts.
7. Stop the backend, then attempt deletion and confirm. Verify an error appears,
   the row remains, and delete controls are re-enabled. Restart the backend and retry.

## Add Sale feature

- PostgreSQL integration suite: **28 passed** (including creation, current decimal price,
  persisted record, refreshed analytics, invalid quantities, missing entities, forbidden
  client total, and numeric overflow). Tests use isolated schemas and roll back their data.
- Backend Ruff check and frontend TypeScript/Vite production build passed.
- Uvicorn startup and live health/options requests passed on port 8001 (8000 was occupied).
- New endpoints: `GET /api/customers`, `GET /api/products`, `POST /api/sales` (201).
- The existing Sale model is unchanged; no migration is required.
- Browser interaction was not verified in this session because no browser was connected.

### Manual Add Sale test

1. Start PostgreSQL and the backend/frontend using the README commands. Open
   `http://localhost:5173` and select Last 30 days. Note total revenue and total orders.
2. Beside Recent sales, click **Add Sale**. Verify customer and product options load.
3. Select a customer and product; note the displayed unit price. Try an empty quantity,
   `0`, `-1`, and `1.5`: submission must be blocked. Cancel and reopen to check reset.
4. Select both options and enter quantity `2`. Click **Save Sale** once. During the
   request, controls must be disabled. The modal should close after success.
5. Verify the newest sale shows that customer/product, quantity 2, and twice the unit
   price. Total orders increases by 1 and total revenue by the returned amount.
   Check today's revenue chart, category totals, and top products where applicable.
6. Reload the browser and verify the record persists. On the Sales page, go to a later
   page, add another sale, and verify pagination returns to the newest records.
7. Stop the backend before opening the form: verify a useful error and Retry button.
   Restart it and retry. Stop it after options load and try saving: the form should
   retain inputs and show an error. Restart it and submit again.
8. In `http://localhost:8000/docs`, POST `/api/sales` with valid IDs and quantity 1:
   expect 201. Try nonexistent customer/product IDs: expect 404. Try quantity 0,
   fractional quantity, missing fields, or an extra `total_amount`: expect 422.

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

## Telegram sale notifications — 2026-10-07

- Baseline suite: 66 passed. Final suite: **139 passed**, including 73 new cases.
  Telegram is mocked throughout; no real bot requests were made.
- Create/update/delete publish immutable events after successful commit/refresh.
  PostgreSQL tests verify ordering, snapshots, rollback/no delivery on failure,
  correct messages and preserved API success/data during Telegram failures.
- Unit tests verify formatting/diffs, optional settings, HTTP/API/JSON/network
  errors, timeout/redirect configuration, secret masking and httpx URL redaction.
- Backend/launcher Ruff, new-file formatter checks, `pip check`, imports and diff
  whitespace checks passed. No backend type checker is configured.
- Temporary Uvicorn startup, live database health, sale OpenAPI routes and missing
  Telegram credentials warning passed; the verification process was stopped.
- Existing TestClient deprecation warning remains. Tests disable pytest's cache
  provider due to local cache permissions. Frontend was unchanged.
- [Architecture, file inventory, commands and limitations](backend/TELEGRAM.md).

