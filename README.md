# Dairy Shop API

FastAPI backend for the dairy shop app, sitting on top of `01_schema.sql`
(the PostgreSQL schema from the earlier milestone). This covers milestone 7
(roles/auth) plus the CRUD, ledger, and recurring-sale endpoints from
milestones 1–6, tested end to end against a live server — see "What's been
tested" below.

## Setup

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```

Create `.env` in this folder:

```
DATABASE_URL=postgresql+psycopg2://<user>:<password>@<host>:5432/<your_db>
JWT_SECRET=<generate something random — e.g. `openssl rand -hex 32`>
```

Load the schema (from wherever you saved `01_schema.sql`):

```bash
psql -U <user> -d <your_db> -f 01_schema.sql
```

Create the first admin and worker accounts (never insert users directly
via SQL — passwords must go through bcrypt):

```bash
./venv/bin/python -m scripts.create_user --username admin --full-name "Owner" --role admin
./venv/bin/python -m scripts.create_user --username worker1 --full-name "Worker One" --role worker
```

Run the server:

```bash
./venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Interactive API docs (every endpoint, try-it-out included) are then at
`http://<host>:8000/docs`.

### A dependency gotcha we hit and fixed

`passlib[bcrypt]` doesn't pin a compatible `bcrypt` version, and current
`bcrypt` (5.x) removed an attribute passlib's version-check reads, which
makes password hashing throw. `requirements.txt` pins `bcrypt==4.0.1`
explicitly to avoid this — don't `pip install --upgrade bcrypt` without
retesting login.

## What's implemented

- **Auth**: JWT login (`POST /auth/login`), `GET /auth/me`.
- **Role enforcement at the API layer**, not just hidden UI (spec §29):
  `require_admin` rejects a worker's valid token with 403. Verified live:
  a worker token gets 403 on `/suppliers/{id}` and `/ledger/{date}`; an
  admin token succeeds on both.
- **Products, suppliers (+ default rates via `supplier_products`),
  customers** — worker-facing list endpoints return name/id only, never
  dues (spec §28); admin-only detail endpoints return the derived balance.
- **Supplier purchases** (optionally with a payment at the same time),
  **supplier payments, sales (cash/credit), customer payments, expenses**
  — create for both roles, edit/delete admin-only, all soft-deleted.
- **Recurring sales**: `POST /recurring-sales`, `POST
  /recurring-sales/generate` (idempotent — verified: 4 rows on first run
  covering 4 missed days, 0 on immediate re-run).
- **Daily ledger**: `GET /ledger/{date}` (admin-only), `POST
  /ledger/cash-anchor` for day-1 or manual opening-cash correction.
- **Bills**: `GET /customers/{id}/bill?period_start=&period_end=` returns
  product-wise totals, grand total, previous due, payments in the period,
  and remaining due — verified against hand-calculated numbers.
- **Idempotency keys** on every transaction insert, so a retried request
  from a flaky mobile connection can't double-charge.
- **No-overpayment guard**: enforced as a deferred Postgres constraint
  trigger, so it holds even against a bug in this API or a future client.
  A rejected write returns a clean `400` with the actual reason — see the
  next section for why that took an extra fix to get right.

## What's been tested (and one real bug this caught)

Every endpoint above was exercised with real HTTP requests against a live
`uvicorn` process and a real Postgres database — not just read for
correctness. That testing caught a genuine bug worth understanding if you
add new write endpoints:

**The bug:** the first version committed the database transaction in a
FastAPI dependency's post-`yield` teardown code. FastAPI/Starlette sends
the HTTP response *before* running that teardown code. So when the
no-overpayment guard (a *deferred* constraint — it only fires at COMMIT)
rejected a huge overpayment, the client had already been sent `200 OK`
with a fake payment ID. The database then silently rolled the write back.
The worker's app would have shown "payment saved" for a payment that
never actually applied — exactly the kind of silent inconsistency the
requirements doc calls out as unacceptable.

**The fix:** `app/deps.py`'s `commit(db)` helper must be called explicitly,
as the *last* step inside each write endpoint, before it returns its
response. That keeps any constraint failure inside the endpoint's own
execution, before FastAPI has built or sent anything — so a rejected
write now correctly comes back as a `400` with the real reason, and
retesting confirmed the balance is provably unchanged afterward.

**If you add a new write endpoint:** use `get_audited_db` for the
session, and call `commit(db)` as the literal last line before `return`.
Skipping it doesn't just risk silent failures the way it did before —
without any commit call at all, the write is lost entirely (an
uncommitted transaction is rolled back when the session closes).

## What's still to build

- **Bill images**: this API returns bill *data* as JSON. Rendering that
  to a shareable PNG/JPEG (spec §18) is a Flutter-side step — e.g. wrap
  the bill widget in a `RepaintBoundary`, capture it, and share via
  `share_plus`. No paid WhatsApp Business API needed for this.
- **Recurring generation trigger**: nothing calls
  `POST /recurring-sales/generate` automatically yet. Options: call it
  once when the admin app opens each day, or run it as a cron/scheduled
  task against the same database.
- **Dashboard/reports endpoints** (spec §32, §38) — the underlying data
  is all queryable from the existing views (`v_customer_balance`,
  `v_supplier_balance`, `v_daily_cash_flow`) and `fn_daily_ledger`;
  these just need thin aggregating endpoints.
- **Refresh tokens** — current JWTs are long-lived (12h) with no refresh
  flow; fine for a single-shift use pattern, worth revisiting if that
  changes.
