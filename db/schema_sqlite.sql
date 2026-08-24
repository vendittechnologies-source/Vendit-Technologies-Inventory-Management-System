-- Vendit Technologies Inventory Management System
-- SQLite schema
--
-- Note: timestamp/date columns (created_at, updated_at, run_date,
-- issued_at, closed_at, etc.) have no SQL-level DEFAULT. The app always
-- supplies these explicitly (see utils.now_str()/today_str()) so the
-- exact same INSERT statements work unchanged against SQLite and
-- PostgreSQL.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin', 'staff')),
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS suppliers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    contact_name TEXT,
    email TEXT,
    phone TEXT,
    address TEXT,
    notes TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

-- Filling captains: the field staff who take stock out to fill vending
-- machines in the morning and bring back unsold stock in the evening.
-- (Referred to informally as "riders" too -- same role.)
CREATE TABLE IF NOT EXISTS captains (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    phone TEXT,
    notes TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

-- Internal teams that can consume stock directly (not via machine filling).
CREATE TABLE IF NOT EXISTS teams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sku TEXT NOT NULL UNIQUE,
    barcode TEXT UNIQUE,
    name TEXT NOT NULL,
    description TEXT,
    category TEXT,
    unit TEXT NOT NULL DEFAULT 'ea',
    cost_price REAL NOT NULL DEFAULT 0,
    sell_price REAL NOT NULL DEFAULT 0,
    reorder_point INTEGER NOT NULL DEFAULT 0,
    quantity_on_hand INTEGER NOT NULL DEFAULT 0,
    default_supplier_id INTEGER REFERENCES suppliers(id) ON DELETE SET NULL,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS purchase_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    po_number TEXT NOT NULL UNIQUE,
    supplier_id INTEGER NOT NULL REFERENCES suppliers(id) ON DELETE RESTRICT,
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'ordered', 'partially_received', 'received', 'cancelled')),
    order_date TEXT,
    expected_date TEXT,
    received_date TEXT,
    notes TEXT,
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS purchase_order_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    purchase_order_id INTEGER NOT NULL REFERENCES purchase_orders(id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
    quantity_ordered INTEGER NOT NULL,
    quantity_received INTEGER NOT NULL DEFAULT 0,
    unit_cost REAL NOT NULL DEFAULT 0
);

-- A captain's morning-to-evening cycle: stock issued to them to fill
-- machines, and whatever they bring back unsold that evening. "Filled"
-- (i.e. actually used/sold) = quantity_issued - quantity_returned.
CREATE TABLE IF NOT EXISTS captain_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    captain_id INTEGER NOT NULL REFERENCES captains(id) ON DELETE RESTRICT,
    run_date TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed')),
    notes TEXT,
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    issued_at TEXT NOT NULL,
    closed_at TEXT
);

CREATE TABLE IF NOT EXISTS captain_run_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES captain_runs(id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
    quantity_issued INTEGER NOT NULL DEFAULT 0,
    quantity_returned INTEGER
);

-- Every stock movement, of any kind, is logged here so quantity_on_hand
-- can always be reconstructed and audited.
--   reason = 'purchase'     (in)  -- from a received purchase order
--   reason = 'return'       (in)  -- captain returning unused stock that evening
--   reason = 'issuance'     (out) -- stock handed to a captain that morning
--   reason = 'consumption'  (out) -- used internally by a team
--   reason = 'damage'       (out) -- written off as damaged
--   reason = 'expiry'       (out) -- written off as expired
--   reason = 'adjustment'   (in or out) -- manual correction, e.g. stock count
CREATE TABLE IF NOT EXISTS stock_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    type TEXT NOT NULL CHECK (type IN ('in', 'out')),
    reason TEXT NOT NULL CHECK (reason IN ('purchase', 'return', 'issuance', 'consumption', 'damage', 'expiry', 'adjustment')),
    quantity INTEGER NOT NULL,
    resulting_quantity INTEGER NOT NULL,
    captain_id INTEGER REFERENCES captains(id) ON DELETE SET NULL,
    team_id INTEGER REFERENCES teams(id) ON DELETE SET NULL,
    purchase_order_id INTEGER REFERENCES purchase_orders(id) ON DELETE SET NULL,
    captain_run_id INTEGER REFERENCES captain_runs(id) ON DELETE SET NULL,
    reference TEXT,
    notes TEXT,
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_transactions_product ON stock_transactions(product_id);
CREATE INDEX IF NOT EXISTS idx_transactions_created ON stock_transactions(created_at);
CREATE INDEX IF NOT EXISTS idx_transactions_reason ON stock_transactions(reason);
CREATE INDEX IF NOT EXISTS idx_po_items_po ON purchase_order_items(purchase_order_id);
CREATE INDEX IF NOT EXISTS idx_po_supplier ON purchase_orders(supplier_id);
CREATE INDEX IF NOT EXISTS idx_products_category ON products(category);
CREATE INDEX IF NOT EXISTS idx_run_items_run ON captain_run_items(run_id);
CREATE INDEX IF NOT EXISTS idx_runs_captain ON captain_runs(captain_id);
