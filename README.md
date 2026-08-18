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

Python 3 + Flask, with SQLite as the database (a single file, no separate
database server to run) and JWT-based login. The frontend is plain HTML/CSS/JS
served by the same app — no build step required.

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
2. In Render: **New → Web Service**, connect the repo.
3. Build command: `pip install -r requirements.txt`
   Start command: `gunicorn app:app --bind 0.0.0.0:$PORT` (already in the `Procfile`)
4. Add environment variables (Render dashboard → Environment):
   - `JWT_SECRET` — a long random string
   - `DEFAULT_ADMIN_USERNAME`, `DEFAULT_ADMIN_PASSWORD` — for the first login
5. **Important — persistent storage:** SQLite writes to a file on disk. Add a
   Render **Disk** (Render dashboard → Disks) mounted at, e.g., `/data`, and
   set an environment variable `DATABASE_PATH=/data/inventory.sqlite` so your
   data survives redeploys. Without a persistent disk, the database resets
   every time you deploy.
6. After the first deploy, open a shell on the service (or run a one-off job)
   and run `python db/seed.py` to create the database tables and the first
   admin account.

### Railway.app

Same idea: connect the repo, Railway will detect the `Procfile`. Add a
**Volume** and set `DATABASE_PATH` to a path inside it, set the same
environment variables as above, then run `python db/seed.py` once via
Railway's shell/CLI.

### A note on scale

SQLite comfortably handles a small team working through a web app like this.
If Vendit later grows to many concurrent locations or a much larger team,
the `db/connection.py` file is the only place that would need to change to
move to Postgres — the rest of the app talks to it through plain SQL.

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
db/schema.sql            Database schema
db/seed.py               Creates tables + the first admin account
routes/                  API endpoints, grouped by area
templates/                One HTML file per page (plain JS, calls the API)
static/                  Shared CSS and JS
```
