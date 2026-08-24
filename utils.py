"""Small shared helpers."""
from datetime import datetime, timezone


def row_to_dict(row):
    if row is None:
        return None
    return dict(row)


def rows_to_list(rows):
    return [dict(r) for r in rows]


def now_str():
    """Current UTC time as 'YYYY-MM-DD HH:MM:SS' -- the format used for
    every stored timestamp and expected by the frontend's date parsing.
    Computed in Python (rather than relying on a database function like
    SQLite's datetime('now') or Postgres's now()) so the exact same query
    text works unchanged against either database."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def today_str():
    """Today's date (UTC) as 'YYYY-MM-DD'."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


class ApiError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.message = message
        self.status = status
