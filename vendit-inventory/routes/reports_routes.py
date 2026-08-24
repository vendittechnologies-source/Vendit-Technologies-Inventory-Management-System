from flask import Blueprint, request, jsonify

from db.connection import get_connection
from auth import require_auth
from utils import rows_to_list, today_str

bp = Blueprint("reports_routes", __name__, url_prefix="/api/reports")


@bp.route("/dashboard", methods=["GET"])
@require_auth
def dashboard():
    conn = get_connection()
    try:
        product_count = conn.execute(
            "SELECT COUNT(*) AS n FROM products WHERE active = 1"
        ).fetchone()["n"]
        low_stock_count = conn.execute(
            "SELECT COUNT(*) AS n FROM products WHERE active = 1 AND quantity_on_hand <= reorder_point"
        ).fetchone()["n"]
        inventory_value = conn.execute(
            "SELECT COALESCE(SUM(quantity_on_hand * cost_price), 0) AS v FROM products WHERE active = 1"
        ).fetchone()["v"]
        open_runs = conn.execute(
            "SELECT COUNT(*) AS n FROM captain_runs WHERE status = 'open'"
        ).fetchone()["n"]
        open_pos = conn.execute(
            "SELECT COUNT(*) AS n FROM purchase_orders WHERE status IN ('draft', 'ordered', 'partially_received')"
        ).fetchone()["n"]
        today_writeoffs = conn.execute(
            "SELECT COALESCE(SUM(quantity), 0) AS n FROM stock_transactions "
            "WHERE reason IN ('damage','expiry') AND substr(created_at, 1, 10) = ?",
            (today_str(),),
        ).fetchone()["n"]

        recent = conn.execute(
            """SELECT t.*, p.name AS product_name, u.full_name AS created_by_name,
                      c.name AS captain_name, tm.name AS team_name
               FROM stock_transactions t
               JOIN products p ON p.id = t.product_id
               LEFT JOIN users u ON u.id = t.created_by
               LEFT JOIN captains c ON c.id = t.captain_id
               LEFT JOIN teams tm ON tm.id = t.team_id
               ORDER BY t.created_at DESC, t.id DESC LIMIT 15"""
        ).fetchall()

        return jsonify(
            {
                "product_count": product_count,
                "low_stock_count": low_stock_count,
                "inventory_value": inventory_value,
                "open_runs": open_runs,
                "open_purchase_orders": open_pos,
                "today_writeoffs": today_writeoffs,
                "recent_activity": rows_to_list(recent),
            }
        )
    finally:
        conn.close()


@bp.route("/low-stock", methods=["GET"])
@require_auth
def low_stock():
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT * FROM products
               WHERE active = 1 AND quantity_on_hand <= reorder_point
               ORDER BY (quantity_on_hand - reorder_point) ASC"""
        ).fetchall()
        return jsonify(rows_to_list(rows))
    finally:
        conn.close()


@bp.route("/valuation", methods=["GET"])
@require_auth
def valuation():
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT id, sku, name, category, quantity_on_hand, cost_price, sell_price,
                      (quantity_on_hand * cost_price) AS cost_value,
                      (quantity_on_hand * sell_price) AS retail_value
               FROM products WHERE active = 1 ORDER BY cost_value DESC"""
        ).fetchall()
        totals = conn.execute(
            """SELECT COALESCE(SUM(quantity_on_hand * cost_price), 0) AS total_cost_value,
                      COALESCE(SUM(quantity_on_hand * sell_price), 0) AS total_retail_value
               FROM products WHERE active = 1"""
        ).fetchone()
        return jsonify({"products": rows_to_list(rows), "totals": dict(totals)})
    finally:
        conn.close()


@bp.route("/captain-summary", methods=["GET"])
@require_auth
def captain_summary():
    """Per-captain totals: issued, returned, filled, and write-offs attributed to them."""
    date_from = request.args.get("from")
    date_to = request.args.get("to")

    date_clause = ""
    params = []
    if date_from:
        date_clause += " AND substr(t.created_at, 1, 10) >= ?"
        params.append(date_from)
    if date_to:
        date_clause += " AND substr(t.created_at, 1, 10) <= ?"
        params.append(date_to)

    conn = get_connection()
    try:
        rows = conn.execute(
            f"""SELECT c.id AS captain_id, c.name AS captain_name,
                       COALESCE(SUM(CASE WHEN t.reason = 'issuance' THEN t.quantity ELSE 0 END), 0) AS total_issued,
                       COALESCE(SUM(CASE WHEN t.reason = 'return' THEN t.quantity ELSE 0 END), 0) AS total_returned,
                       COALESCE(SUM(CASE WHEN t.reason = 'damage' THEN t.quantity ELSE 0 END), 0) AS total_damaged,
                       COALESCE(SUM(CASE WHEN t.reason = 'expiry' THEN t.quantity ELSE 0 END), 0) AS total_expired
                FROM captains c
                LEFT JOIN stock_transactions t ON t.captain_id = c.id {date_clause}
                WHERE c.active = 1
                GROUP BY c.id, c.name
                ORDER BY c.name"""
            , params,
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["total_filled"] = d["total_issued"] - d["total_returned"]
            result.append(d)
        return jsonify(result)
    finally:
        conn.close()


@bp.route("/consumption-by-team", methods=["GET"])
@require_auth
def consumption_by_team():
    date_from = request.args.get("from")
    date_to = request.args.get("to")
    date_clause = ""
    params = []
    if date_from:
        date_clause += " AND substr(t.created_at, 1, 10) >= ?"
        params.append(date_from)
    if date_to:
        date_clause += " AND substr(t.created_at, 1, 10) <= ?"
        params.append(date_to)

    conn = get_connection()
    try:
        rows = conn.execute(
            f"""SELECT tm.id AS team_id, tm.name AS team_name,
                       COALESCE(SUM(t.quantity), 0) AS total_consumed
                FROM teams tm
                LEFT JOIN stock_transactions t ON t.team_id = tm.id AND t.reason = 'consumption' {date_clause}
                WHERE tm.active = 1
                GROUP BY tm.id, tm.name
                ORDER BY tm.name""",
            params,
        ).fetchall()
        return jsonify(rows_to_list(rows))
    finally:
        conn.close()
