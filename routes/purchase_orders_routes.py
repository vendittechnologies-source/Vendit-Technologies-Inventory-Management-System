from datetime import datetime

from flask import Blueprint, request, jsonify, g

from db.connection import get_connection
from auth import require_auth, require_role
from utils import ApiError, rows_to_list
from stock_ops import apply_stock_change

bp = Blueprint("po_routes", __name__, url_prefix="/api/purchase-orders")


def _next_po_number(conn):
    year = datetime.now().strftime("%Y")
    prefix = f"PO-{year}-"
    row = conn.execute(
        "SELECT po_number FROM purchase_orders WHERE po_number LIKE ? ORDER BY id DESC LIMIT 1",
        (f"{prefix}%",),
    ).fetchone()
    if row:
        last_seq = int(row["po_number"].split("-")[-1])
    else:
        last_seq = 0
    return f"{prefix}{last_seq + 1:04d}"


def _po_with_items(conn, po_id):
    po = conn.execute(
        """SELECT po.*, s.name AS supplier_name, u.full_name AS created_by_name
           FROM purchase_orders po
           JOIN suppliers s ON s.id = po.supplier_id
           LEFT JOIN users u ON u.id = po.created_by
           WHERE po.id = ?""",
        (po_id,),
    ).fetchone()
    if not po:
        return None
    items = conn.execute(
        """SELECT poi.*, p.name AS product_name, p.sku, p.unit
           FROM purchase_order_items poi
           JOIN products p ON p.id = poi.product_id
           WHERE poi.purchase_order_id = ?
           ORDER BY p.name""",
        (po_id,),
    ).fetchall()
    result = dict(po)
    result["items"] = rows_to_list(items)
    return result


@bp.route("", methods=["GET"])
@require_auth
def list_pos():
    status = request.args.get("status")
    conn = get_connection()
    try:
        sql = """SELECT po.*, s.name AS supplier_name,
                         (SELECT COUNT(*) FROM purchase_order_items WHERE purchase_order_id = po.id) AS item_count
                  FROM purchase_orders po JOIN suppliers s ON s.id = po.supplier_id WHERE 1=1"""
        params = []
        if status:
            sql += " AND po.status = ?"
            params.append(status)
        sql += " ORDER BY po.created_at DESC LIMIT 200"
        rows = conn.execute(sql, params).fetchall()
        return jsonify(rows_to_list(rows))
    finally:
        conn.close()


@bp.route("/<int:po_id>", methods=["GET"])
@require_auth
def get_po(po_id):
    conn = get_connection()
    try:
        result = _po_with_items(conn, po_id)
        if not result:
            return jsonify({"error": "Purchase order not found."}), 404
        return jsonify(result)
    finally:
        conn.close()


@bp.route("", methods=["POST"])
@require_auth
def create_po():
    data = request.get_json(silent=True) or {}
    supplier_id = data.get("supplier_id")
    items = data.get("items") or []
    order_date = data.get("order_date")
    expected_date = data.get("expected_date")
    notes = data.get("notes")

    if not supplier_id:
        return jsonify({"error": "A supplier is required."}), 400
    if not items:
        return jsonify({"error": "Add at least one line item."}), 400

    conn = get_connection()
    try:
        supplier = conn.execute("SELECT id FROM suppliers WHERE id = ?", (supplier_id,)).fetchone()
        if not supplier:
            return jsonify({"error": "Supplier not found."}), 404

        po_number = _next_po_number(conn)
        cur = conn.execute(
            """INSERT INTO purchase_orders
               (po_number, supplier_id, status, order_date, expected_date, notes, created_by)
               VALUES (?, ?, 'draft', ?, ?, ?, ?)""",
            (po_number, supplier_id, order_date, expected_date, notes, g.user["id"]),
        )
        po_id = cur.lastrowid

        for item in items:
            product_id = item.get("product_id")
            qty = item.get("quantity_ordered") or item.get("quantity")
            unit_cost = item.get("unit_cost") or 0
            if not product_id or not qty or qty <= 0:
                raise ApiError("Each line item needs a product and a positive quantity.")
            conn.execute(
                """INSERT INTO purchase_order_items (purchase_order_id, product_id, quantity_ordered, unit_cost)
                   VALUES (?, ?, ?, ?)""",
                (po_id, product_id, qty, unit_cost),
            )

        conn.commit()
        return jsonify(_po_with_items(conn, po_id)), 201
    except ApiError as e:
        conn.rollback()
        return jsonify({"error": e.message}), e.status
    finally:
        conn.close()


@bp.route("/<int:po_id>/status", methods=["PATCH"])
@require_auth
def update_po_status(po_id):
    data = request.get_json(silent=True) or {}
    new_status = data.get("status")
    if new_status not in ("draft", "ordered", "cancelled"):
        return jsonify({"error": "Status must be 'draft', 'ordered', or 'cancelled'."}), 400

    conn = get_connection()
    try:
        po = conn.execute("SELECT * FROM purchase_orders WHERE id = ?", (po_id,)).fetchone()
        if not po:
            return jsonify({"error": "Purchase order not found."}), 404
        if po["status"] in ("received", "cancelled"):
            return jsonify({"error": f"Can't change status of a {po['status']} order."}), 400

        conn.execute(
            "UPDATE purchase_orders SET status = ?, updated_at = datetime('now') WHERE id = ?",
            (new_status, po_id),
        )
        conn.commit()
        return jsonify(_po_with_items(conn, po_id))
    finally:
        conn.close()


@bp.route("/<int:po_id>/receive", methods=["POST"])
@require_auth
def receive_po(po_id):
    """Record goods received against a PO. Adds stock and updates status
    to 'partially_received' or 'received' depending on whether everything
    ordered has now arrived."""
    data = request.get_json(silent=True) or {}
    receipts = {item["product_id"]: item.get("quantity_received", 0) for item in (data.get("items") or [])}

    conn = get_connection()
    try:
        po = conn.execute("SELECT * FROM purchase_orders WHERE id = ?", (po_id,)).fetchone()
        if not po:
            return jsonify({"error": "Purchase order not found."}), 404
        if po["status"] in ("received", "cancelled"):
            return jsonify({"error": f"This order is already {po['status']}."}), 400

        po_items = conn.execute(
            "SELECT * FROM purchase_order_items WHERE purchase_order_id = ?", (po_id,)
        ).fetchall()

        for poi in po_items:
            qty_now = int(receipts.get(poi["product_id"], 0) or 0)
            if qty_now < 0:
                raise ApiError("Received quantity can't be negative.")
            remaining = poi["quantity_ordered"] - poi["quantity_received"]
            if qty_now > remaining:
                raise ApiError(
                    f"Can't receive {qty_now} — only {remaining} still outstanding for product #{poi['product_id']}."
                )
            if qty_now > 0:
                apply_stock_change(
                    conn, poi["product_id"], "in", qty_now, "purchase", g.user["id"],
                    purchase_order_id=po_id, reference=po["po_number"],
                )
                conn.execute(
                    "UPDATE purchase_order_items SET quantity_received = quantity_received + ? WHERE id = ?",
                    (qty_now, poi["id"]),
                )

        refreshed_items = conn.execute(
            "SELECT * FROM purchase_order_items WHERE purchase_order_id = ?", (po_id,)
        ).fetchall()
        fully_received = all(i["quantity_received"] >= i["quantity_ordered"] for i in refreshed_items)
        any_received = any(i["quantity_received"] > 0 for i in refreshed_items)
        new_status = "received" if fully_received else ("partially_received" if any_received else po["status"])

        conn.execute(
            "UPDATE purchase_orders SET status = ?, received_date = CASE WHEN ? = 'received' THEN date('now') ELSE received_date END, "
            "updated_at = datetime('now') WHERE id = ?",
            (new_status, new_status, po_id),
        )
        conn.commit()
        return jsonify(_po_with_items(conn, po_id))
    except ApiError as e:
        conn.rollback()
        return jsonify({"error": e.message}), e.status
    finally:
        conn.close()
