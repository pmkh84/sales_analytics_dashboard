# USD/Toman exchange rate

This feature displays a market quote only. Product prices, sale calculations,
database records and Telegram subscriptions/notifications retain their existing behavior.

## Request flow

```text
App dashboard header -> ExchangeRateCard -> useExchangeRate
  -> existing Axios API service -> GET /api/exchange-rate
  -> synchronous router -> shared ExchangeRateService
  -> valid in-process cache OR Navasan HTTPS latest API (usd_buy)
  -> backend Toman normalization -> ExchangeRate schema -> card
```

The UI initially loads independently of analytics, polls every two minutes while
the tab is visible, and refetches when the existing dashboard refresh revision
changes. Requests are cancelled on replacement/unmount. No provider credentials
or requests reach the frontend. No new dependency, worker or Redis service is needed.

## Provider and currency semantics

[Navasan's official API guide](https://www.navasan.tech/api/webserviceguide/)
documents the `usd_buy` latest endpoint and its `value` and Unix `timestamp` fields.
The [official rate page](https://www.navasan.net/dayRates.php?item=usd_buy) labels
these Tehran market sell quotes in Toman. This is a more suitable regional market
quote for this display than an indicative official USD/IRR currency quote.

The adapter explicitly treats this provider as `IRT`, leaving its value unchanged.
The normalization helper also supports explicit `IRR`, dividing by ten, with tests
for both currencies. It never guesses the unit from the value's magnitude. No other
provider adapter is implemented. API output always uses `base=USD`, `quote=IRT`,
`source=Navasan`. Invalid, nonpositive, nonfinite or excessively large rates and
missing/invalid/future timestamps are rejected. The update time is provider time,
serialized as UTC and displayed in Asia/Tehran, with the full date in the tooltip.

The [provider's plan page](https://www.navasan.tech/api/) documents a limited trial
(120 calls/month, two-hour updates, three months) and paid plans. At the default
TTL, continuous use can consume 30 calls/hour per API process and exhaust that trial
quickly. Select a plan or increase the TTL. Market closures and provider plan delays
can leave the timestamp old despite a successful API response.

## Backend configuration

Set these in `backend/.env` or the backend process environment; restart after changes.
Do not put them in frontend `VITE_*` settings.

| Setting | Default / purpose |
| --- | --- |
| `EXCHANGE_RATE_API_KEY` | Empty; backend-only Navasan credential, optional for application startup |
| `EXCHANGE_RATE_API_URL` | `https://api.navasan.tech/latest/`; HTTPS URL without embedded credentials, query or fragment |
| `EXCHANGE_RATE_CACHE_TTL_SECONDS` | `120`; 1–86400 seconds, also throttles retries after failures |
| `EXCHANGE_RATE_TIMEOUT_SECONDS` | `5`; positive, at most 30 seconds, HTTP operation timeout |

## Cache and failure behavior

The service singleton is created by a cached FastAPI dependency. A lock prevents
concurrent requests from duplicating a provider fetch. Monotonic time controls the
TTL, starting after the fetch attempt. A fresh cached response makes no HTTP call.
An expired cache refreshes on the next request; there is no scheduled backend task.

A successful refresh replaces the value and clears `stale`. Timeout, non-2xx,
invalid JSON/data or missing configuration returns the previous value with
`stale=true`, preserving its original provider timestamp. Without any successful
cached value, the endpoint returns HTTP 503 with
`{"detail":"Exchange rate unavailable. Try again later."}`. Failed attempts also
wait one TTL before another attempt. A subsequent successful attempt recovers normally.

Warnings contain only a fixed reason, numeric HTTP status and cache presence.
Provider bodies, URLs, exception text and credentials are excluded. The credential
uses Pydantic `SecretStr`; the httpx request logger redacts `api_key` query values.
Redirect following is disabled so the query credential is not forwarded elsewhere.

Cache data is lost on restart and is independent in each API process/worker.
Last-known data has no maximum age; it stays explicitly marked stale through an
outage. `stale=false` means the latest fetch succeeded, not that the market timestamp
is within the TTL. This distinction avoids inventing a provider update time.

## File inventory

| File | Change / responsibility |
| --- | --- |
| `backend/app/services/exchange_rate.py` | New: provider adapter, normalization, validation, cache, safe logging and fallback |
| `backend/app/routers/exchange_rate.py` | New: read-only endpoint and dependency injection |
| `backend/tests/test_exchange_rate.py` | New: mocked provider/cache/configuration/API tests |
| `frontend/src/hooks/useExchangeRate.ts` | New: independent state, refresh, polling and cancellation |
| `frontend/src/components/ExchangeRateCard.tsx` | New: loading, success, stale and unavailable card |
| `backend/EXCHANGE_RATE.md` | New: architecture, configuration, inventory and verification guide |
| `backend/app/config.py` | Modified: optional validated exchange settings |
| `backend/app/schemas/__init__.py` | Modified: immutable typed exchange-rate response |
| `backend/app/main.py` | Modified: register the new router |
| `backend/.env.example` | Modified: empty credential and defaults |
| `frontend/src/services/api.ts` | Modified: centralized typed backend GET with cancellation and 10-second timeout |
| `frontend/src/types/index.ts` | Modified: response interface |
| `frontend/src/App.tsx` | Modified: card in Dashboard header, outside analytics loading/error handling |
| `frontend/src/index.css` | Modified: card and responsive header styles |
| `README.md` | Modified: feature, setup and endpoint documentation |
| `VERIFICATION.md` | Modified: verified results and remaining limitations |

## Run and verify

From the repository root, run the existing stack with `.\dev.cmd` after configuring
the optional backend key. The launcher starts Docker PostgreSQL, FastAPI and Vite.
Open `http://localhost:5173`; inspect `http://localhost:8000/api/exchange-rate`.

Commands used for automated checks (PowerShell, repository root unless noted):

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests -q -p no:cacheprovider
.\.venv\Scripts\python.exe -m pytest backend/tests/test_exchange_rate.py -q -p no:cacheprovider
.\.venv\Scripts\python.exe -m ruff check backend scripts
.\.venv\Scripts\python.exe -m ruff format --check backend/app/services/exchange_rate.py backend/app/routers/exchange_rate.py backend/tests/test_exchange_rate.py
git diff --check
cd frontend
npm.cmd run typecheck
npm.cmd run build
npm.cmd exec -- prettier --check src/App.tsx src/services/api.ts src/types/index.ts src/hooks/useExchangeRate.ts src/components/ExchangeRateCard.tsx src/index.css
```

All 217 backend tests passed, including 42 exchange-rate cases. Provider calls are
mocked: parsing, explicit Rial/Toman normalization, TTL boundary/custom TTL,
concurrency, stale fallback, retry throttling/recovery, missing key, malformed data,
timeouts, HTTP errors/redirects, endpoint shape and sanitized failures are covered.
Settings validation and query-log redaction are also tested.

The existing React/esbuild dependencies rendered the real card with isolated hook
states; all four states, thousands separators, Persian currency label and Tehran
time from the backend timestamp passed. No frontend testing framework was added.
A temporary Uvicorn process on port 18001 verified startup, route registration,
live database health and missing-key HTTP 503, with provider and Telegram delivery
disabled for that verification process. It was stopped afterward.

TypeScript, Vite, Ruff, formatting and whitespace checks passed. Scope checks compare
pre-change file hashes: business models, analytics/sales services, Telegram code,
sales components and currency formatting are unchanged. Local `.env` files were
not modified; example credentials remain empty.

## Remaining checks and limitations

No authenticated live Navasan request was made; configure a valid key and verify
provider availability, HTTPS access, quota and your plan's update frequency before
demoing live quotes. No rate is fabricated when access fails.

Browser automation reported no available browser. Card output was checked through
React rendering, but visual desktop/mobile layout and real browser interaction
remain to be checked. For a browser smoke check, inspect the card at desktop and
390px widths; throttle the exchange request for loading, use a valid key for
success, simulate a provider failure after TTL for Last known rate, then restart
with an empty key for unavailable. Confirm charts/sales still load in every state.

The existing Starlette TestClient/httpx deprecation warning remains; it does not
affect test results. The UI rate request has a 10-second timeout; a backend timeout
configured above that can cause the UI to report unavailable before the server
finishes its attempt.
