# Historical exchange-rate-aware pricing

## Architecture and precision

Products retain `price NUMERIC(12,2)` in USD. Sales retain `total_amount NUMERIC(14,2)`
in USD for compatibility and add nullable `exchange_rate_toman NUMERIC(20,6)` and
`total_amount_toman NUMERIC(32,2)`. No extra USD column duplicates `total_amount`.
The database constraint permits either both new fields null (legacy), or both
present with a positive rate, nonnegative Toman total and
`total_amount_toman = round(total_amount * exchange_rate_toman, 2)`.

Provider numeric JSON is parsed directly as Decimal, not binary float. Rate values
are rounded to six decimal places using `ROUND_HALF_UP` before multiplication,
so the exact saved rate produces the exact saved total. Toman totals and AOV round
half-up to two decimals. USD multiplication uses the existing two-decimal product
price. Rate quantization, Toman multiplication and AOV use a 40-digit Decimal context. Unsupported totals
return 422; a positive provider quote rounding to zero at six decimals is unusable
and returns 503. Existing rate upper bound remains one trillion Toman per USD.

All API money/rate fields serialize as exact JSON strings. Backend money never
passes through float. Growth is calculated from Decimal sums and exposed as a
numeric percentage. Frontend product/sale/KPI formatting groups Decimal strings
with BigInt, preserving cents above JavaScript's safe-integer range. Recharts needs
numeric coordinates: the centralized API layer converts aggregate revenue strings
only for chart plotting and percentages. Those chart coordinates/tooltips are
approximate at very large magnitudes; no frontend conversion determines saved prices.

## Create, update and delete

```text
POST business inputs -> sales service validates customer/product
  -> USD product price x quantity; check USD capacity
  -> shared cached ExchangeRateService -> usable Decimal quote
  -> quantize rate -> USD total x saved rate -> rounded Toman total
  -> insert all financial fields -> flush snapshot -> commit -> refresh
  -> publish SaleCreated -> notification handler -> existing Telegram broadcast
```

The client supplies only customer/product IDs and quantity; extra financial fields
are forbidden. A fresh or intentionally stale cached quote is accepted under the
existing service policy. Missing usable quotes return a sanitized 503 before adding
or mutating any sale. SQLAlchemy write failures roll back all fields and publish
no event. Delivery failures still cannot undo a successful business commit.

PATCH validates the existing sale/customer/product. Changing product ID or quantity
uses the current product USD price and current usable rate, replacing all three
saved financial values together. Changing customer alone, or saving unchanged
inputs, preserves the original USD total, historical rate and Toman total—even if
the catalog price or current rate changed. This also preserves null legacy values.
An actual product/quantity edit to a legacy row prices it at edit time; this is an
intentional financial edit, not a historical backfill. The sale ID/date stay unchanged.
Previous/current immutable snapshots are published through `SaleUpdated` after
commit/refresh. Delete captures the persisted amounts before deletion, commits,
then publishes `SaleDeleted`; it does not need the current rate.

## Dynamic product prices versus historical sales

`GET /api/products` returns compatibility `price`, explicit `price_usd`, dynamic
`price_toman` and `exchange_rate_stale`. It uses one shared quote for the whole
response and does not write product prices. Provider failure without a quote leaves
the catalog readable with `price_toman=null`; the form shows price unavailable.

Create/update and recent-sale responses return USD `total_amount`, saved
`exchange_rate_toman` and saved `total_amount_toman`. Reads never fetch a quote or
recompute historical totals. For example (illustrative amounts, not live quotes):

```json
{"total_amount":"2.00","exchange_rate_toman":"100.000000","total_amount_toman":"200.00"}
```

A later rate of 150 produces a new sale total of 300, while the first stays 200.
The current product quote becomes 300 independently of that first sale.

## Analytics and legacy coverage

Revenue, previous-period revenue, trends, category sums and top-product rankings
sum `Sale.total_amount_toman` directly in PostgreSQL. They do not fetch a quote or
sum USD and convert afterward. Summary includes `currency=IRT`, `priced_orders`,
`legacy_orders` and `previous_legacy_orders`. AOV uses priced orders only; total
orders/customer counts and category/product quantities include all applicable rows.

Null historical amounts are excluded rather than treated as known zero-valued sales.
Empty priced sums return zero in API aggregates, with explicit coverage counts;
the UI displays unavailable money KPIs if all selected sales are legacy and provides
a coverage banner. Growth is null if prior priced revenue is zero or either period
contains legacy rows. AI context declares IRT and the same coverage definitions;
instructions prohibit guessing missing amounts/rates.

The sales table shows saved Toman amounts or a legacy-unavailable label. The form
shows current Toman unit prices and a stale indication when applicable. KPIs,
chart axes/tooltips and footer now use Toman; the USD/Toman utility card remains a
currency-pair display. Telegram includes historical Toman/optional USD and rate
from event snapshots, with old/new changes on edits and explicit legacy labels.
Subscription/webhook/transport architecture is unchanged.

## Migration and seed strategy

The repository has no Alembic migration setup; previously it used `create_all`,
which cannot add columns to an existing table. `app.migrate` is a small additive,
transactional, idempotent migration under the existing schema advisory lock. It
initializes missing tables, adds both nullable columns without a default and adds
the consistency constraint. It does not drop/reset data or assign old rates.
Run it before starting an upgraded backend. The existing seed/launcher invokes it
as well. Concurrent running installations should be restarted after deployment.

The configured database contained 1,500 sales, 30 products, 100 customers and two
subscribers. The migration was applied and original row-content digests matched
before/after for every table. All 1,500 sales retain their USD totals and have null
historical rate/Toman fields. Migration and seed reruns preserved all rows.

Seeded dates have no trustworthy rate history. Updated seed code explicitly creates
legacy rows; it does not invent historical financial data. This means existing/seed
analytics cannot display complete historical Toman revenue. Configure the provider
to create new priced sales. Resetting/reseeding does not solve missing historical
quotes and is not required. There is no destructive down migration.

## User-approved fixed rate for legacy sales

On 2026-10-10, the user approved **267,000 Toman per USD** for legacy sales
without saved pricing. This is an assigned conversion rate, not a verified market
quote for each original sale date.

Run from `backend/` using the project virtual environment:

```powershell
..\.venv\Scripts\python.exe -m app.backfill_legacy_pricing
```

The command ensures the schema exists and, within one transaction, updates only
sales where both `exchange_rate_toman` and `total_amount_toman` are null. It
multiplies the original saved USD total (including any discount) by 267,000 using
PostgreSQL decimal arithmetic. It preserves existing priced sales, USD totals,
quantities, dates, products and customers. A repeat run updates zero rows unless
additional unpriced legacy rows have been imported. It does not fetch a provider
quote or publish sale notifications. Reads and analytics use the saved backfilled
amounts, so those sales now count toward Toman revenue and average order value.

The schema migration and seed still do not assign historical rates automatically;
run this explicit command for an existing database or after seeding demo data.
The legacy-unavailable behavior described above applies to rows that have not
been backfilled. A local before-update snapshot is stored under `.local/backups/`.

## Files and responsibilities

New files:

| File | Responsibility |
| --- | --- |
| `backend/app/migrate.py` | Additive nullable columns/constraint, transactional CLI |
| `backend/app/services/pricing.py` | Shared Decimal quote validation, quantization, multiplication/capacity |
| `backend/tests/test_historical_pricing.py` | Isolated PostgreSQL historical pricing and migration scenarios |
| `backend/HISTORICAL_PRICING.md` | Architecture, precision, inventory, commands and limitations |

Modified files:

| File | Responsibility |
| --- | --- |
| `backend/app/models/__init__.py` | Historical sale fields and consistency constraint |
| `backend/app/services/sales.py` | Atomic create/reprice, non-financial preservation, dynamic catalog quote |
| `backend/app/services/analytics.py` | Saved Toman aggregation and legacy coverage |
| `backend/app/services/exchange_rate.py` | Exact Decimal JSON parsing/response, retain existing Navasan `usd_buy` adapter/cache |
| `backend/app/config.py` | Correct malformed default URL; credential remains a separate query parameter |
| `backend/app/schemas/__init__.py` | Decimal response fields, product prices and coverage metadata |
| `backend/app/events.py` | Immutable historical rate/Toman snapshot fields |
| `backend/app/notifications/service.py` | Format persisted Toman totals/rates and legacy indications |
| `backend/app/ai/service.py` | IRT and legacy coverage instructions |
| `backend/app/seed.py` | Run migration, explicitly retain legacy seed rows |
| `backend/tests/test_api.py` | Mock quotes, Decimal assertions/contracts, preserve unchanged edits |
| `backend/tests/test_exchange_rate.py` | Decimal API contract and exact numeric JSON parsing |
| `backend/tests/test_notifications.py` | Legacy formatter expectations, isolated optional settings |
| `frontend/src/types/index.ts` | Exact Decimal-string responses and coverage fields |
| `frontend/src/services/api.ts` | Typed wire responses, chart coordinate conversion |
| `frontend/src/utils/format.ts` | Exact grouped Toman strings and chart axis formatting |
| `frontend/src/components/SaleForm.tsx` | Dynamic Toman unit quote and edit policy note |
| `frontend/src/components/SalesTable.tsx` | Saved historical Toman/legacy display |
| `frontend/src/components/KpiCards.tsx` | Toman KPIs, priced AOV, incomplete comparison/unavailable states |
| `frontend/src/components/Charts.tsx` | Toman summary type and wider currency axis |
| `frontend/src/components/Layout.tsx` | Toman/legacy footer label |
| `frontend/src/components/ExchangeRateCard.tsx` | Decimal-string display, correct existing buy-rate label |
| `frontend/src/App.tsx` | Current/previous legacy coverage banner |
| `README.md` | Setup, migration, currency and metric semantics |
| `backend/EXCHANGE_RATE.md` | Shared pricing service and Decimal response documentation |
| `backend/TELEGRAM.md` | Persisted Toman message semantics |
| `VERIFICATION.md` | Results and outstanding live/visual checks |

## Commands

PowerShell, from repository root:

```powershell
# Existing installation: additive migration, safe rerun of initialization/seed.
cd backend
..\.venv\Scripts\python.exe -m app.migrate
..\.venv\Scripts\python.exe -m app.seed
cd ..

.\.venv\Scripts\python.exe -m pytest backend/tests -q -p no:cacheprovider
.\.venv\Scripts\python.exe -m pytest backend/tests/test_historical_pricing.py -q -p no:cacheprovider
.\.venv\Scripts\python.exe -m ruff check backend scripts
git diff --check

cd frontend
npm.cmd run typecheck
npm.cmd run build
npm.cmd exec -- prettier --check src/App.tsx src/types/index.ts src/services/api.ts src/utils/format.ts src/components/Charts.tsx src/components/ExchangeRateCard.tsx src/components/SalesTable.tsx src/components/SaleForm.tsx src/components/Layout.tsx src/components/KpiCards.tsx
cd ..
.\dev.cmd
```

The changed backend files were also checked/formatted with `python -m ruff format`.
No new environment variable or dependency is needed; configure the existing backend
exchange provider key to price sales. The corrected default endpoint has no query;
the service supplies `api_key` and the already-selected `usd_buy` item separately.
No local `.env` file was edited.

## Verification and limits

Automated tests mock all provider and Telegram calls and use rolled-back temporary
PostgreSQL schemas. Coverage includes product USD preservation, 100/150 rate
history, quantity/product edits, customer-only/no-op preservation, stale quotes,
rate quantization, unusable rate/write failure rollback, client financial-field
rejection, historical sums/AOV/growth, product quote changes, legacy behavior,
immutable notification values, database consistency and migration idempotency.
The full backend suite passed **241 tests**: 22 dedicated historical-pricing cases
and 44 exchange-service cases, alongside existing sales, analytics, subscription,
delivery and launcher regressions. TypeScript, Vite production build, Ruff and
changed-file formatting/whitespace checks passed.

A temporary real Uvicorn HTTP server created two sales at mocked rates 100/150,
returned 200/300 from later reads, and returned historical revenue 500/AOV 250 and
trend sum 500. Its schema and all smoke writes rolled back, and its process stopped.
React/esbuild checks verified exact grouping beyond JavaScript safe integers,
fractions, very large chart values, Toman KPIs and all-legacy unavailable states.

Authenticated live provider access, live paid AI, real Telegram delivery and visual
desktop/mobile browser interaction were not verified. Provider quota/update delay,
per-process cache and indefinite marked-stale fallback still follow the existing
exchange-rate service. Accepted stale quotes are recorded as their exact saved rate;
this minimal schema does not separately persist quote source/time/stale status.
Legacy rows remain excluded until trustworthy historical data is supplied or an
explicit financial edit prices the sale. Existing TestClient deprecation warning remains.
