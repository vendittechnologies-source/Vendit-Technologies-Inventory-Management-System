"""Create the database tables and a default admin account, if one doesn't exist.

Run with:  python db/seed.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from werkzeug.security import generate_password_hash
from db.connection import get_connection, init_db
from utils import now_str


def seed():
    init_db()
    conn = get_connection()
    try:
        existing = conn.execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1").fetchone()
        if existing:
            print("An admin user already exists — skipping default admin creation.")
            return

        username = os.environ.get("DEFAULT_ADMIN_USERNAME", "admin")
        password = os.environ.get("DEFAULT_ADMIN_PASSWORD", "ChangeMe123!")
        full_name = "Administrator"

        conn.execute(
            "INSERT INTO users (username, password_hash, full_name, role, active, created_at) "
            "VALUES (?, ?, ?, 'admin', 1, ?)",
            (username, generate_password_hash(password), full_name, now_str()),
        )
        conn.commit()
        print(f"Created default admin user '{username}'.")
        print("IMPORTANT: log in and change this password immediately.")
    finally:
        conn.close()


if __name__ == "__main__":
    seed()
