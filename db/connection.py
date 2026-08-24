"""Database connection helpers for the Vendit Inventory app.

Uses SQLite by default -- zero setup, so the app runs and tests instantly
on a laptop with nothing else installed. When a DATABASE_URL environment
variable is present (e.g. a managed Postgres database attached on Render),
it switches to PostgreSQL automatically -- giving production a real
concurrent, persistent database without losing the ability to develop and
test against SQLite locally.

Every route in this app talks to the database through conn.execute(sql,
params), same as the sqlite3 module's convenience API. The PGConnection
class below wraps a real psycopg2 connection so it exposes that same
small surface, translating SQLite's '?' placeholders to psycopg2's '%s'
and emulating cursor.lastrowid (which psycopg2/Postgres doesn't provide
natively) via an automatic `RETURNING id` on plain INSERT statements.
"""
import os
import re
import sqlite3

DATABASE_URL = os.environ.get("DATABASE_URL")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SQLITE_DB_PATH = os.environ.get(
    "DATABASE_PATH", os.path.join(BASE_DIR, "inventory.sqlite")
)

_PLACEHOLDER_RE = re.compile(r"\?")


def using_postgres():
    return bool(DATABASE_URL)


# ---------------------------------------------------------------------
# PostgreSQL backend
# ---------------------------------------------------------------------

class _PGCursorResult:
    """Exposes just the subset of the sqlite3 cursor API this codebase
    uses (.fetchone / .fetchall / .lastrowid), backed by a psycopg2
    cursor."""

    __slots__ = ("_cursor", "lastrowid")

    def __init__(self, cursor, lastrowid=None):
        self._cursor = cursor
        self.lastrowid = lastrowid

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()


class PGConnection:
    """Wraps a psycopg2 connection so conn.execute(sql, params) keeps
    working exactly like sqlite3's, for every route in this app."""

    def __init__(self, pg_conn):
        self._conn = pg_conn

    def execute(self, sql, params=None):
        import psycopg2.extras

        translated = _PLACEHOLDER_RE.sub("%s", sql)
        stripped = translated.strip()
        needs_id = (
            stripped[:6].upper() == "INSERT" and "RETURNING" not in stripped.upper()
        )
        if needs_id:
            translated = stripped.rstrip().rstrip(";") + " RETURNING id"

        cursor = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute(translated, params if params is not None else [])

        lastrowid = None
        if needs_id:
            row = cursor.fetchone()
            lastrowid = row["id"] if row else None

        return _PGCursorResult(cursor, lastrowid=lastrowid)

    def executescript(self, sql):
        cursor = self._conn.cursor()
        cursor.execute(sql)
        cursor.close()

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()


def _get_postgres_connection():
    import psycopg2

    dsn = DATABASE_URL
    if dsn and "sslmode" not in dsn and "localhost" not in dsn and "127.0.0.1" not in dsn:
        dsn = dsn + ("&" if "?" in dsn else "?") + "sslmode=require"
    pg_conn = psycopg2.connect(dsn)
    return PGConnection(pg_conn)


# ---------------------------------------------------------------------
# SQLite backend
# ---------------------------------------------------------------------

def _get_sqlite_connection():
    conn = sqlite3.connect(SQLITE_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ---------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------

def get_connection():
    if using_postgres():
        return _get_postgres_connection()
    return _get_sqlite_connection()


def init_db():
    """Create tables if they don't already exist."""
    schema_file = "schema_postgres.sql" if using_postgres() else "schema_sqlite.sql"
    schema_path = os.path.join(BASE_DIR, schema_file)
    with open(schema_path, "r") as f:
        schema = f.read()
    conn = get_connection()
    try:
        conn.executescript(schema)
        conn.commit()
    finally:
        conn.close()
