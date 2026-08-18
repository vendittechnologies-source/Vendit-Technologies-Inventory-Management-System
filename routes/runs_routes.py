"""Captain runs: morning issuance of stock to a filling captain, and the
evening return/close, from which "filled" (issued - returned) is derived."""
from flask import Blueprint, request, jsonify, g

from db.connection import get_connection
from auth import require_auth
from utils import ApiError, rows_to_list
from stock_ops import apply_stock_change

bp = Blueprint("runs_routes", __name__, url_prefix="/api/captain-runs")


def _run_with_items(conn, run_id):
    run = conn.execute(
        """SELECT r.*, c.name AS captain_name, u.full_name AS created_by_name
           FROM captain_runs r
           JOIN captains c ON c.id = r.captain_id
           LEFT JOIN users u ON u.id = r.created_by
           WHERE r.id = ?""",
        (run_id,),
    ).fetchone()
    if not run:
        return None
    items = conn.execute(
        """SELECT ri.*, p.name AS product_name, p.sku, p.unit
           FROM captain_run_items ri
           JOIN products p ON p.id = ri.product_id
           WHERE ri.run_id = ?
           ORDER BY p.name""",
        (run_id,),
    ).fetchall()
    result = dict(run)
    result["items"] = [
        {
            **dict(item),
            "quantity_filled": (
                item["quantity_issued"] - item["quantity_returned"]
                if item["quantity_returned"] is not None
                else None
            ),
        }
        for item in items
    ]
    return result


@bp.route("", methods=["GET"])
@require_auth
def list_runs():
    status = request.args.get("status")
    captain_id = request.args.get("captain_id")
    conn = get_connection()
    try:
        sql = """SELECT r.*, c.name AS captain_name,
                         (SELECT COUNT(*) FROM captain_run_items WHERE run_id = r.id) AS item_count
                  FROM captain_runs r JOIN captains c ON c.id = r.captain_id WHERE 1=1"""
        params = []
        if status:
            sql += " AND r.status = ?"
            params.append(status)
        if captain_id:
            sql += " AND r.captain_id = ?"
            params.append(captain_id)
        sql += " ORDER BY r.issued_at DESC LIMIT 200"
        rows = conn.execute(sql, params).fetchall()
        return jsonify(rows_to_list(rows))
    finally:
        conn.close()


@bp.route("/<int:run_id>", methods=["GET"])
@require_auth
def get_run(run_id):
    conn = get_connection()
    try:
        result = _run_with_items(conn, run_id)
        if not result:
            return jsonify({"error": "Run not found."}), 404
        return jsonify(result)
    finally:
        conn.close()


@bp.route("", methods=["POST"])
@require_auth
def create_run():
    data = request.get_json(silent=True) or {}
    captain_id = data.get("captain_id")
    items = data.get("items") or []
    run_date = data.get("run_date")
    notes = data.get("notes")

    if not captain_id:
        return jsonify({"error": "A filling captain is required."}), 400
    if not items:
        return jsonify({"error": "Add at least one product to issue."}), 400

    conn = get_connection()
    try:
        captain = conn.execute(
            "SELECT id FROM captains WHERE id = ? AND active = 1", (captain_id,)
        ).fetchone()
        if not captain:
            return jsonify({"error": "Filling captain not found or inactive."}), 404

        cur = conn.execute(
            """INSERT INTO captain_runs (captain_id, run_date, status, notes, created_by)
               VALUES (?, COALESCE(?, date('now')), 'open', ?, ?)""",
            (captain_id, run_date, notes, g.user["id"]),
        )
        run_id = cur.lastrowid

        for item in items:
            product_id = item.get("product_id")
            qty = item.get("quantity_issued") or item.get("quantity")
            if not product_id or not qty or qty <= 0:
                raise ApiError("Each item needs a product and a positive quantity.")

            apply_stock_change(
                conn, product_id, "out", qty, "issuance", g.user["id"],
                captain_id=captain_id, captain_run_id=run_id,
                reference=f"Run #{run_id}",
            )
            conn.execute(
                """INSERT INTO captain_run_items (run_id, product_id, quantity_issued)
                   VALUES (?, ?, ?)""",
                (run_id, product_id, qty),
            )

        conn.commit()
        return jsonify(_run_with_items(conn, run_id)), 201
    except ApiError as e:
        conn.rollback()
        return jsonify({"error": e.message}), e.status
    finally:
        conn.close()


@bp.route("/<int:run_id>/close", methods=["POST"])
@require_auth
def close_run(run_id):
    data = request.get_json(silent=True) or {}
    returns = {item["product_id"]: item.get("quantity_returned", 0) for item in (data.get("items") or [])}
    notes = data.get("notes")

    conn = get_connection()
    try:
        run = conn.execute("SELECT * FROM captain_runs WHERE id = ?", (run_id,)).fetchone()
        if not run:
            return jsonify({"error": "Run not found."}), 404
        if run["status"] == "closed":
            return jsonify({"error": "This run has already been closed."}), 400

        run_items = conn.execute(
            "SELECT * FROM captain_run_items WHERE run_id = ?", (run_id,)
        ).fetchall()

        for ri in run_items:
            returned_qty = int(returns.get(ri["product_id"], 0) or 0)
            if returned_qty < 0:
                raise ApiError("Returned quantity can't be negative.")
            if returned_qty > ri["quantity_issued"]:
                raise ApiError(
                    f"Returned quantity ({returned_qty}) can't exceed what was issued "
                    f"({ri['quantity_issued']}) for product #{ri['product_id']}."
                )
            if returned_qty > 0:
                apply_stock_change(
                    conn, ri["product_id"], "in", returned_qty, "return", g.user["id"],
                    captain_id=run["captain_id"], captain_run_id=run_id,
                    reference=f"Run #{run_id}",
                )
            conn.execute(
                "UPDATE captain_run_items SET quantity_returned = ? WHERE id = ?",
                (returned_qty, ri["id"]),
            )

        conn.execute(
            "UPDATE captain_runs SET status = 'closed', closed_at = datetime('now'), "
            "notes = COALESCE(?, notes) WHERE id = ?",
            (notes, run_id),
        )
        conn.commit()
        return jsonify(_run_with_items(conn, run_id))
    except ApiError as e:
        conn.rollback()
        return jsonify({"error": e.message}), e.status
    finally:
        conn.close()
