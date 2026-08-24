"""Simple lookup lists: filling captains and internal teams."""
from flask import Blueprint, request, jsonify

from db.connection import get_connection
from auth import require_auth, require_role
from utils import rows_to_list, now_str

captains_bp = Blueprint("captains_routes", __name__, url_prefix="/api/captains")
teams_bp = Blueprint("teams_routes", __name__, url_prefix="/api/teams")
suppliers_bp = Blueprint("suppliers_routes", __name__, url_prefix="/api/suppliers")


def _register_simple_lookup(bp, table, extra_columns):
    """Register GET/POST/PATCH for a simple id/name(+extra) lookup table."""

    @bp.route("", methods=["GET"], endpoint=f"{table}_list")
    @require_auth
    def list_items():
        include_inactive = request.args.get("include_inactive") == "1"
        conn = get_connection()
        try:
            sql = f"SELECT * FROM {table}"
            if not include_inactive:
                sql += " WHERE active = 1"
            sql += " ORDER BY name"
            rows = conn.execute(sql).fetchall()
            return jsonify(rows_to_list(rows))
        finally:
            conn.close()

    @bp.route("", methods=["POST"], endpoint=f"{table}_create")
    @require_auth
    @require_role("admin")
    def create_item():
        data = request.get_json(silent=True) or {}
        name = (data.get("name") or "").strip()
        if not name:
            return jsonify({"error": "Name is required."}), 400
        cols = ["name"] + extra_columns + ["created_at"]
        vals = [name] + [data.get(c) for c in extra_columns] + [now_str()]
        placeholders = ", ".join(["?"] * len(cols))
        conn = get_connection()
        try:
            cur = conn.execute(
                f"INSERT INTO {table} ({', '.join(cols)}, active) VALUES ({placeholders}, 1)",
                vals,
            )
            conn.commit()
            return jsonify({"id": cur.lastrowid}), 201
        except Exception as e:  # unique constraint etc.
            return jsonify({"error": str(e)}), 409
        finally:
            conn.close()

    @bp.route("/<int:item_id>", methods=["PATCH"], endpoint=f"{table}_update")
    @require_auth
    @require_role("admin")
    def update_item(item_id):
        data = request.get_json(silent=True) or {}
        editable = ["name", "active"] + extra_columns
        fields, params = [], []
        for f in editable:
            if f in data:
                fields.append(f"{f} = ?")
                params.append(data[f])
        if not fields:
            return jsonify({"error": "Nothing to update."}), 400
        params.append(item_id)
        conn = get_connection()
        try:
            conn.execute(f"UPDATE {table} SET {', '.join(fields)} WHERE id = ?", params)
            conn.commit()
            return jsonify({"ok": True})
        finally:
            conn.close()


_register_simple_lookup(captains_bp, "captains", ["phone", "notes"])
_register_simple_lookup(teams_bp, "teams", [])
_register_simple_lookup(
    suppliers_bp, "suppliers", ["contact_name", "email", "phone", "address", "notes"]
)
