# Telegram sale notifications

The backend uses synchronous FastAPI routes, SQLAlchemy services and PostgreSQL.
Sale services publish immutable application events after their existing database
commit (and, for create/update, refresh) completes. An in-process notification
handler formats those events and calls a dedicated synchronous `httpx` client for
each active PostgreSQL subscriber. HTTP communication stays in the client;
the webhook router delegates subscription behavior to the notification service.

## Configuration

Set these in **backend/.env** or backend process environment variables. The root
.env belongs to Docker Compose; frontend environment variables are public and
must never contain these credentials. Restart the backend after changing settings.

| Variable | Default | Responsibility |
| --- | --- | --- |
| `TELEGRAM_BOT_TOKEN` | Empty | Server-side bot credential, stored as Pydantic `SecretStr`. |
| `TELEGRAM_ENABLED` | `true` | Set `false` to disable delivery even with credentials present. |
| `TELEGRAM_API_URL` | `https://api.telegram.org` | HTTPS API base URL; supports an optional proxy path. Credentials, query strings and fragments are rejected. |
| `TELEGRAM_TIMEOUT_SECONDS` | `3` | HTTP timeout per network phase; greater than zero, at most 30 seconds. |

Blank or whitespace-only bot tokens disable delivery and produce one warning
per application process at startup. Explicit disabling logs at INFO. No HTTP
request occurs during initialization. Render users can set the same optional
variables directly in their backend service's environment settings.

`TELEGRAM_CHAT_ID` is no longer used; any existing value in local .env files is
ignored. Destinations come exclusively from active subscriber records. A stopped
subscriber therefore cannot receive notifications through a configured fallback.

## Open demo subscriptions

Any Telegram user can subscribe automatically. There are no invitation codes,
shared subscription secrets, authentication checks, authorization checks, chat
allowlists or approval steps. The webhook has no secret-token header requirement.

- `/start`: PostgreSQL upsert by chat ID, activate the subscription, refresh
  available chat metadata, commit, then send a short subscription confirmation.
  Repeated starts keep one record. Missing metadata preserves existing values.
- `/stop`: mark the existing record inactive, commit, then confirm. An unknown chat
  also receives the confirmation without creating an active subscription.
- `/start@BotName` and optional command arguments work without an invitation code.
  Other commands and non-text updates are acknowledged and ignored.

Records retain signed 64-bit chat IDs, active state, chat type, available username,
first name, last name, group title and timestamps. Subscriber metadata is never
added to sale messages or failure logs. Every sale event queries current active
subscriptions. Recipient failures are isolated so delivery continues to the rest.
Confirmation failures preserve the committed state. With delivery disabled,
subscription state can still be updated but no confirmation can be sent.

### Receive bot commands

Incoming commands use `POST /api/telegram/webhook`. Publish the backend at a public
HTTPS URL or expose the local backend through a public HTTPS tunnel. Telegram
cannot reach the local `localhost:8000` address directly. This implementation uses
[Telegram webhooks](https://core.telegram.org/bots/api#setwebhook), not polling.

From the repository root, initialize the added table using the project's existing
idempotent schema command, then register your actual public URL:

```powershell
cd backend
..\.venv\Scripts\python.exe -m app.seed
..\.venv\Scripts\python.exe -m app.notifications.webhook https://YOUR_PUBLIC_BACKEND/api/telegram/webhook
```

`app.seed` creates the subscriber table even when existing demo sales cause data
insertion to be skipped. It preserves existing records. The dev launcher and
Render startup already run this initialization command.

The registration command reads the bot token from backend settings, so no token
goes into shell arguments or printed output. It calls `setWebhook` with message
updates and one concurrent webhook connection; it does not set `secret_token`.
No webhook registration or real bot messages are performed by automated tests.
After registration, send `/start` to the bot, perform a sale action, then send
`/stop` to opt out. Only bot configuration and network routing are required.

Delivery uses [Telegram's sendMessage API](https://core.telegram.org/bots/api#sendmessage)
with JSON `chat_id`, `text` and disabled link previews. No parse mode is used:
product names are plain text, whitespace is collapsed, and names are bounded to
keep messages below the API's 4096-character limit. Messages show the saved historical
Toman total, USD base total and saved rate. Legacy rows explicitly show unavailable
Toman values. Formatting and deletion never fetch a current quote. Money uses two
decimals; rates display up to six. Messages include sale ID, customer ID,
product name/ID, category, quantity and total. Customer names/emails, timestamps,
credentials and raw objects are excluded. Update messages list only changed
business values with old → new values. An unchanged save gets an explicit
“No business values changed” message.

## Event flows

| Action | Complete flow |
| --- | --- |
| Create / record sold product | `POST /api/sales` → validate customer/product and calculate decimal total → add/flush → capture immutable values and generated ID → commit → refresh → `SaleCreated` → handler → “Sale Created (Sold)” → Telegram client → `sendMessage` → existing 201 response. |
| Update | `PATCH /api/sales/{id}` → validate and calculate current-price total → capture previous values → set fields and capture new values → commit → refresh → `SaleUpdated` → handler → changed fields → client → `sendMessage` → existing 200 response. |
| Delete | `DELETE /api/sales/{id}` → find sale and capture its values/product before deletion → delete → commit → `SaleDeleted` → handler → deleted sale details → client → `sendMessage` → existing 204 response. |
| Sold / status change | The existing model has no status field or separate sold action. Creating a `Sale` already records a completed sale; it emits one `SaleCreated` notification covering this flow. No new status endpoint, schema or migration was added. |

Validation, flush or commit failure skips event publication. SQLAlchemy failures
retain the existing rollback/503 behavior. Telegram HTTP errors (including rate
limits), API rejection, malformed JSON, network failures, and unexpected handler
exceptions preserve successful API responses and committed data.

Known Telegram failures log event type, sale ID, a safe reason and HTTP status when
available. Unexpected handler errors log only the exception class and event
identity. Response bodies, exception messages, tracebacks, chat IDs and bot tokens
are never included in these logs. A filter redacts the bot credential from httpx's
INFO request URL logs. Settings representations hide credentials, and validation
errors hide input values. Existing `.gitignore` rules already protect local .env
files; no real credentials were added to the examples or tests.

## Created files

| File | Responsibility |
| --- | --- |
| `app/events.py` | Immutable sale snapshots, typed create/update/delete events and a failure-isolating publisher. |
| `app/notifications/__init__.py` | Notification package. |
| `app/notifications/service.py` | Message formatting, event handler, cached configuration-based composition and safe failure logs. |
| `app/notifications/telegram.py` | Synchronous Telegram HTTP communication, sanitized transport/API errors and request URL redaction. |
| `app/notifications/subscriptions.py` | Incoming update schemas, automatic start/stop persistence and active recipient lookup. |
| `app/notifications/webhook.py` | Backend-only CLI for webhook registration. |
| `app/routers/telegram.py` | Open webhook endpoint delegating to subscription logic. |
| `tests/test_notifications.py` | Mocked unit cases for formatting, transport, recipient isolation, confirmations, settings and webhook registration. |
| `TELEGRAM.md` | Configuration, architecture, file inventory, commands, verification and limitations. |

## Modified files

Paths below are relative to the repository root.

| File | Responsibility of the change |
| --- | --- |
| `backend/app/config.py` | Optional Telegram settings, secret masking, HTTPS URL/timeout validation and safe settings errors. |
| `backend/app/models/__init__.py` | Persistent subscriber model with unique 64-bit chat IDs and Telegram metadata. |
| `backend/app/main.py` | Lifespan initialization so missing integration configuration is reported at startup. |
| `backend/app/services/sales.py` | Capture immutable values and publish events after successful commits/refreshes. |
| `backend/tests/test_api.py` | Block real delivery; PostgreSQL cases for sale events, open subscriptions, metadata, confirmations, rollback and active-only broadcasts. |
| `backend/.env.example` | Optional backend-only Telegram placeholders and defaults. |
| `backend/requirements.txt` | Declare the existing `httpx==0.28.1` dependency directly for production. It is already present in the lock file and installed environment. |
| `README.md` | Telegram configuration reference. |
| `VERIFICATION.md` | Recorded feature validation results. |

## Run and test

From the repository root, with the existing virtual environment and PostgreSQL:

```powershell
# Install the pinned test environment, if needed.
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-lock.txt

# Run the existing local database/backend/frontend launcher.
.\dev.cmd
```

Alternatively, with PostgreSQL already running, start only the backend:

```powershell
cd backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

In a separate terminal, run these from the repository root:

```powershell
.\.venv\Scripts\python.exe -m ruff check backend scripts
.\.venv\Scripts\python.exe -m ruff format --check backend/app/events.py backend/app/notifications backend/tests/test_notifications.py
.\.venv\Scripts\python.exe -m pip check
git diff --check
cd backend
..\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
# Notification unit tests alone do not require a running database.
..\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/test_notifications.py
```

The full suite requires PostgreSQL and permission to create temporary schemas.
Integration fixtures use unique schemas and roll back their contents, preserving
application data. Telegram HTTP calls use `httpx.MockTransport`; synthetic markers
are used as credentials. Existing API tests also mock notification handlers even
when a developer has configured real credentials. No real Telegram requests occur.

## Verified on 2026-10-07

- Original baseline: 66 existing tests. Final suite with open subscriptions:
  **175 passed**, including **43 notification unit cases**. Telegram HTTP calls
  and webhook registration are mocked.
- Coverage includes structured create/delete messages, update diffs, unchanged
  updates, untrusted text, successful `sendMessage` payloads, HTTP/API/JSON/network
  failures, redirects rejected, safe logs/settings, optional configuration, all
  existing sale actions, commit/refresh ordering, validation/flush/commit failure,
  rollback, and persisted business success despite notification failures.
- Subscription coverage includes unrestricted start/stop, large and negative chat
  IDs, idempotent registration, metadata updates/preservation, reactivation,
  unknown stops, ignored updates, confirmation ordering/failure isolation,
  rollback, disabled delivery, active-only broadcasts and live recipient queries.
- Ruff checks for backend and launcher, formatting checks for new Python files,
  `pip check`, and `git diff --check` passed. Imports were exercised by tests and
  actual application startup. No backend type checker is configured.
- A temporary hidden Uvicorn process started against the existing PostgreSQL,
  returned healthy database status, exposed create/update/delete in OpenAPI with
  no Telegram configuration exposed, logged the missing-credentials warning, and
  was stopped. This check performed no business mutations or seed operations.
- Local root/backend/frontend .env files remain ignored. No real Telegram delivery
  was attempted. Frontend code and dependencies were unchanged; no frontend build
  was needed for this backend feature.
- Initialized the new subscriber table in the configured demo database and
  verified existing customer/product/sale counts were unchanged. A temporary
  backend process also accepted an ignored update at the open webhook without
  authentication or subscriber mutations. The registration CLI help passed.

The existing Starlette TestClient/httpx deprecation warning remains. Cache writing
was restricted in this environment, so tests used `-p no:cacheprovider`.

## Compromises and future improvements

Delivery is synchronous and best effort, matching the existing backend style. It
adds network latency to successful requests; the timeout bounds each HTTP phase,
not total wall time. There are no retries, durable queue, new workers, or new
infrastructure. Each notification uses a short-lived HTTP client, avoiding shared
client lifecycle and concurrent access concerns for this small application.

Snapshots are taken before commit expires ORM attributes (or removes deleted
records); events are published afterward. Create/update retain the existing
post-commit refresh. If refresh fails, their API response still follows the
existing 503 path even though commit may have succeeded; no notification is sent.
Direct ORM writes and demo seeding bypass the sale services and do not emit events.

A crash between commit and publication can lose a notification. Timeouts can
leave delivery outcome uncertain. Concurrent operations may deliver out of order.
Webhook command processing intentionally has no durable update deduplication;
repeated starts keep one subscriber row but may repeat confirmations. Commands
are processed in receipt order. Webhook registration uses one connection to keep
this demo simple; durable ordering/deduplication can be added later if needed.
A future transactional outbox with a worker, delivery tracking, backoff/rate-limit
handling and idempotency would address these limits. They were deliberately left
unimplemented as requested. A real status transition should emit its own event
only when such an operation is actually introduced into the business model.

An unrelated existing issue found during testing: a completely malformed
`DATABASE_URL` such as `invalid` raises SQLAlchemy `ArgumentError` directly from
the existing validator instead of a Pydantic `ValidationError`. The local
launcher's validation error handling therefore does not cover that input. This
was left unchanged.
