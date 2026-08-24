"""Manual stock movements that aren't part of a captain run:
internal team consumption, damage/expiry write-offs, and admin corrections."""
from flask import Blueprint, request, jsonify, g

from db.connection import get_connection
from auth import require_auth, require_role
from utils import ApiError, rows_to_list
from stock_ops import apply_stock_change

bp = Blueprint("stock_routes", __name__, url_prefix="/api/stock")


@bp.route("/consumption", methods=["POST"])
@require_auth
def log_consumption():
    data = request.get_json(silent=True) or {}
    product_id = data.get("product_id")
    team_id = data.get("team_id")
    quantity = data.get("quantity")
    notes = data.get("notes")

    if not product_id or not team_id or not quantity:
        return jsonify({"error": "Product, team, and quantity are required."}), 400

    conn = get_connection()
    try:
        team = conn.execute("SELECT id FROM teams WHERE id = ?", (team_id,)).fetchone()
        if not team:
            return jsonify({"error": "Team not found."}), 404

        apply_stock_change(
            conn, product_id, "out", quantity, "consumption", g.user["id"],
            team_id=team_id, notes=notes,
        )
        conn.commit()
        return jsonify({"ok": True}), 201
    except ApiError as e:
        conn.rollback()
        return jsonify({"error": e.message}), e.status
    finally:
        conn.close()


@bp.route("/writeoff", methods=["POST"])
@require_auth
def log_writeoff():
    data = request.get_json(silent=True) or {}
    product_id = data.get("product_id")
    reason = data.get("reason")  # 'damage' or 'expiry'
    quantity = data.get("quantity")
    captain_id = data.get("captain_id")  # who the loss is attributed to (optional)
    notes = data.get("notes")

    if reason not in ("damage", "expiry"):
        return jsonify({"error": "Reason must be 'damage' or 'expiry'."}), 400
    if not product_id or not quantity:
        return jsonify({"error": "Product and quantity are required."}), 400

    conn = get_connection()
    try:
        if captain_id:
            captain = conn.execute("SELECT id FROM captains WHERE id = ?", (captain_id,)).fetchone()
            if not captain:
                return jsonify({"error": "Filling captain not found."}), 404

        apply_stock_change(
            conn, product_id, "out", quantity, reason, g.user["id"],
            captain_id=captain_id, notes=notes,
        )
        conn.commit()
        return jsonify({"ok": True}), 201
    except ApiError as e:
        conn.rollback()
        return jsonify({"error": e.message}), e.status
    finally:
        conn.close()


@bp.route("/adjustment", methods=["POST"])
@require_auth
@require_role("admin")
def log_adjustment():
    data = request.get_json(silent=True) or {}
    product_id = data.get("product_id")
    direction = data.get("direction")  # 'in' or 'out'
    quantity = data.get("quantity")
    notes = data.get("notes")

    if direction not in ("in", "out"):
        return jsonify({"error": "Direction must be 'in' or 'out'."}), 400
    if not product_id or not quantity:
        return jsonify({"error": "Product and quantity are required."}), 400

    conn = get_connection()
    try:
        apply_stock_change(
            conn, product_id, direction, quantity, "adjustment", g.user["id"],
            notes=notes or "Manual stock count correction", allow_negative=True,
        )
        conn.commit()
        return jsonify({"ok": True}), 201
    except ApiError as e:
        conn.rollback()
        return jsonify({"error": e.message}), e.status
    finally:
        conn.close()


@bp.route("/transactions", methods=["GET"])
@require_auth
def list_transactions():
    """Full stock movement history, with filters, for the transactions log page."""
    reason = request.args.get("reason")
    captain_id = request.args.get("captain_id")
    team_id = request.args.get("team_id")
    product_id = request.args.get("product_id")
    date_from = request.args.get("from")
    date_to = request.args.get("to")

    sql = """SELECT t.*, p.name AS product_name, p.sku, u.full_name AS created_by_name,
                     c.name AS captain_name, tm.name AS team_name
              FROM stock_transactions t
              JOIN products p ON p.id = t.product_id
              LEFT JOIN users u ON u.id = t.created_by
              LEFT JOIN captains c ON c.id = t.captain_id
              LEFT JOIN teams tm ON tm.id = t.team_id
              WHERE 1=1"""
    params = []
    if reason:
        sql += " AND t.reason = ?"
        params.append(reason)
    if captain_id:
        sql += " AND t.captain_id = ?"
        params.append(captain_id)
    if team_id:
        sql += " AND t.team_id = ?"
        params.append(team_id)
    if product_id:
        sql += " AND t.product_id = ?"
        params.append(product_id)
    if date_from:
        sql += " AND substr(t.created_at, 1, 10) >= ?"
        params.append(date_from)
    if date_to:
        sql += " AND substr(t.created_at, 1, 10) <= ?"
        params.append(date_to)
    sql += " ORDER BY t.created_at DESC, t.id DESC LIMIT 500"

    conn = get_connection()
    try:
        rows = conn.execute(sql, params).fetchall()
        return jsonify(rows_to_list(rows))
    finally:
        conn.close()
