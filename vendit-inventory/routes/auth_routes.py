from flask import Blueprint, request, jsonify, g
from werkzeug.security import generate_password_hash, check_password_hash

from db.connection import get_connection
from auth import generate_token, require_auth, require_role
from utils import row_to_dict, rows_to_list, now_str

bp = Blueprint("auth_routes", __name__, url_prefix="/api/auth")
users_bp = Blueprint("users_routes", __name__, url_prefix="/api/users")


@bp.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    if not username or not password:
        return jsonify({"error": "Username and password are required."}), 400

    conn = get_connection()
    try:
        user = conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
        if not user or not check_password_hash(user["password_hash"], password):
            return jsonify({"error": "Invalid username or password."}), 401
        if not user["active"]:
            return jsonify({"error": "This account has been deactivated."}), 403

        token = generate_token(user)
        return jsonify(
            {
                "token": token,
                "user": {
                    "id": user["id"],
                    "username": user["username"],
                    "full_name": user["full_name"],
                    "role": user["role"],
                },
            }
        )
    finally:
        conn.close()


@bp.route("/me", methods=["GET"])
@require_auth
def me():
    return jsonify({"user": g.user})


@bp.route("/change-password", methods=["POST"])
@require_auth
def change_password():
    data = request.get_json(silent=True) or {}
    current_password = data.get("current_password") or ""
    new_password = data.get("new_password") or ""
    if not new_password or len(new_password) < 8:
        return jsonify({"error": "New password must be at least 8 characters."}), 400

    conn = get_connection()
    try:
        user = conn.execute(
            "SELECT * FROM users WHERE id = ?", (g.user["id"],)
        ).fetchone()
        if not user or not check_password_hash(user["password_hash"], current_password):
            return jsonify({"error": "Current password is incorrect."}), 401
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (generate_password_hash(new_password), user["id"]),
        )
        conn.commit()
        return jsonify({"ok": True})
    finally:
        conn.close()


# ---- Admin-only user management ----

@users_bp.route("", methods=["GET"])
@require_auth
@require_role("admin")
def list_users():
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, username, full_name, role, active, created_at FROM users ORDER BY username"
        ).fetchall()
        return jsonify(rows_to_list(rows))
    finally:
        conn.close()


@users_bp.route("", methods=["POST"])
@require_auth
@require_role("admin")
def create_user():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    full_name = (data.get("full_name") or "").strip()
    password = data.get("password") or ""
    role = data.get("role") or "staff"

    if not username or not full_name or not password:
        return jsonify({"error": "Username, full name, and password are required."}), 400
    if role not in ("admin", "staff"):
        return jsonify({"error": "Role must be 'admin' or 'staff'."}), 400
    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters."}), 400

    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT id FROM users WHERE username = ?", (username,)
        ).fetchone()
        if existing:
            return jsonify({"error": "That username is already taken."}), 409

        cur = conn.execute(
            "INSERT INTO users (username, password_hash, full_name, role, active, created_at) "
            "VALUES (?, ?, ?, ?, 1, ?)",
            (username, generate_password_hash(password), full_name, role, now_str()),
        )
        conn.commit()
        return jsonify({"id": cur.lastrowid}), 201
    finally:
        conn.close()


@users_bp.route("/<int:user_id>", methods=["PATCH"])
@require_auth
@require_role("admin")
def update_user(user_id):
    data = request.get_json(silent=True) or {}
    conn = get_connection()
    try:
        user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user:
            return jsonify({"error": "User not found."}), 404

        fields = []
        params = []
        if "full_name" in data:
            fields.append("full_name = ?")
            params.append(data["full_name"])
        if "role" in data:
            if data["role"] not in ("admin", "staff"):
                return jsonify({"error": "Role must be 'admin' or 'staff'."}), 400
            fields.append("role = ?")
            params.append(data["role"])
        if "active" in data:
            fields.append("active = ?")
            params.append(1 if data["active"] else 0)
        if "password" in data and data["password"]:
            if len(data["password"]) < 8:
                return jsonify({"error": "Password must be at least 8 characters."}), 400
            fields.append("password_hash = ?")
            params.append(generate_password_hash(data["password"]))

        if not fields:
            return jsonify({"error": "Nothing to update."}), 400

        params.append(user_id)
        conn.execute(f"UPDATE users SET {', '.join(fields)} WHERE id = ?", params)
        conn.commit()
        return jsonify({"ok": True})
    finally:
        conn.close()
