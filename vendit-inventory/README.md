# Vendit Technologies — Inventory Management System

A web-based inventory system built for how Vendit actually runs stock: purchases
from suppliers, filling captains taking stock out to restock vending machines
and bringing back what's unsold, internal team consumption, and damage/expiry
write-offs — all logged against a single source of truth for stock on hand.

## What it tracks

- **Products** — SKUs, barcodes, categories, cost/sell price, reorder points.
- **Filling Captains** — the field staff (also called "riders") who take stock
  out in the morning to fill machines and return unsold stock in the evening.
- **Captain Runs** — one issuance + return cycle per captain per day. "Stock
  filled" is calculated automatically as issued minus returned.
- **Teams** — internal teams that consume stock directly (not via machines).
- **Suppliers & Purchase Orders** — place orders, receive stock against them
  (partial receiving supported), and stock is added automatically on receipt.
- **Damage / Expiry write-offs** — logged against a product and, optionally,
  a specific filling captain for accountability.
- **Reports** — low-stock alerts, inventory valuation, per-captain summary
  (issued/returned/filled/damaged/expired), consumption by team, and a full
  searchable movement history.
- **Users & roles** — every action is tied to a logged-in user. Admins can
  manage products, suppliers, prices, users, and manual stock corrections;
  staff can run the day-to-day flows (runs, consumption, write-offs, POs).

Every single stock movement — of any kind — is written to one
`stock_transactions` table, so quantity on hand can always be reconstructed
and audited.

## Tech stack

Python 3 + Flask, with JWT-based login. The frontend is plain HTML/CSS/JS
served by the same app — no build step required.

The database is dual-backend: **SQLite** by default (a single file, zero setup
— great for local development) and **PostgreSQL** automatically whenever a
`DATABASE_URL` environment variable is present (this is how Render's managed
Postgres databases identify themselves). Every route talks to the database
through the same plain SQL either way — `db/connection.py` is the only file
that knows which database is actually in use.

## Running it locally

```bash
cd vendit-inventory
python3 -m venv venv && source venv/bin/activate   # optional but recommended
pip install -r requirements.txt

cp .env.example .env
# open .env and set JWT_SECRET to a long random string, and change
# DEFAULT_ADMIN_PASSWORD before you seed the database

python db/seed.py      # creates the database and the first admin login
python app.py           # starts the app at http://localhost:3000
```

This uses SQLite by default — nothing else to install. If you want to develop
against Postgres locally instead, install PostgreSQL, create a database, and
set `DATABASE_URL=postgresql://user:password@localhost:5432/dbname` in `.env`
before running `python db/seed.py`.

Log in with the username/password you set as `DEFAULT_ADMIN_USERNAME` /
`DEFAULT_ADMIN_PASSWORD` in `.env` (defaults to `admin` / `ChangeMe123!` if
you don't set them — **change this password immediately after your first
login**, from the account menu).

## Deploying so your team can access it from anywhere

This app is a standard Flask app and deploys to any Python-friendly host.
Render and Railway are the simplest options — both offer a free/low-cost tier
and detect the `Procfile` and `requirements.txt` automatically.

### Render.com

1. Push this project to a GitHub repository.
2. In Render: **New → PostgreSQL**, create a database (any name, the free
   tier is fine to start). Once it's up, open it and copy the **Internal
   Database URL** — you'll need it in step 5.
   > Render's free Postgres databases expire after 90 days. When that
   > happens Render prompts you to create a new one — worth setting a
   > calendar reminder, or upgrading to a paid instance once this is in
   > real use, since a paid database doesn't expire and comes with backups.
3. In Render: **New → Web Service**, connect the repo.
4. Build command: `pip install -r requirements.txt`
   Start command: `gunicorn app:app --bind 0.0.0.0:$PORT` (already in the `Procfile`)
5. Add environment variables (Render dashboard → Environment):
   - `JWT_SECRET` — a long random string
   - `DEFAULT_ADMIN_USERNAME`, `DEFAULT_ADMIN_PASSWORD` — for the first login
   - `DATABASE_URL` — the Internal Database URL you copied in step 2. This is
     what switches the app from SQLite to Postgres — as soon as it's set,
     every table gets created in Postgres instead, and data persists across
     redeploys and restarts on its own (no disk/volume needed, unlike SQLite).
6. Deploy. The first startup creates the tables and the first admin account
   automatically — you don't need to run `python db/seed.py` by hand on
   Render (it runs at app startup either way, and does nothing once an admin
   already exists).

If you'd rather stay on SQLite for a very small/single-user deployment, just
skip step 2 and don't set `DATABASE_URL` — but then add a Render **Disk**
mounted at, e.g., `/data`, and set `DATABASE_PATH=/data/inventory.sqlite`, or
your data will be wiped on every redeploy.

### Railway.app

Same idea: connect the repo, Railway will detect the `Procfile`. Add a
Railway **Postgres** plugin and it will set `DATABASE_URL` for you
automatically; set the other environment variables above the same way.

### A note on scale

The app already runs on real, concurrent-safe PostgreSQL in production (see
the Render steps above) rather than a single SQLite file — that's the change
that matters most for scaling to more users and more simultaneous captains/
staff working at once. SQLite remains the default for local development
because it needs no setup, but nothing about moving further (more instances,
a bigger team, higher traffic) requires touching the database layer again;
it's already backed by Postgres in the environment where it counts.

## Changing branding

The name "Vendit Technologies" appears in `static/js/app.js` (`renderShell`)
and in `templates/login.html`. Update those two spots if this ever needs to
be white-labelled.

## Future: barcode scanning

Every product has a `barcode` field, and there's already an API endpoint
(`GET /api/products/barcode/<code>`) that looks a product up by barcode. A
USB or Bluetooth barcode scanner acts as a keyboard, so the fastest way to
add scanning later is to add a barcode input box to the relevant forms
(e.g. the "add product to run" row) that calls this endpoint on each scan
and auto-fills the product — no hardware integration code needed beyond that.

## Project structure

```
app.py                   Flask app entry point, registers all routes
auth.py                  JWT issuing/verification, login-required decorators
stock_ops.py             The one function that changes quantity_on_hand + logs it
db/connection.py         Picks SQLite vs Postgres based on DATABASE_URL
db/schema_sqlite.sql     Database schema (SQLite)
db/schema_postgres.sql   Database schema (PostgreSQL) — kept in sync with the SQLite one
db/seed.py               Creates tables + the first admin account
routes/                  API endpoints, grouped by area
templates/                One HTML file per page (plain JS, calls the API)
static/                  Shared CSS and JS
```
