from flask import Blueprint, request, jsonify, g

from db.connection import get_connection
from auth import require_auth, require_role
from utils import rows_to_list, now_str

bp = Blueprint("products_routes", __name__, url_prefix="/api/products")


@bp.route("", methods=["GET"])
@require_auth
def list_products():
    q = request.args.get("q", "").strip()
    category = request.args.get("category", "").strip()
    low_stock_only = request.args.get("low_stock") == "1"
    include_inactive = request.args.get("include_inactive") == "1"

    conn = get_connection()
    try:
        sql = "SELECT * FROM products WHERE 1=1"
        params = []
        if not include_inactive:
            sql += " AND active = 1"
        if q:
            sql += " AND (name LIKE ? OR sku LIKE ? OR barcode LIKE ?)"
            like = f"%{q}%"
            params += [like, like, like]
        if category:
            sql += " AND category = ?"
            params.append(category)
        if low_stock_only:
            sql += " AND quantity_on_hand <= reorder_point"
        sql += " ORDER BY name"
        rows = conn.execute(sql, params).fetchall()
        return jsonify(rows_to_list(rows))
    finally:
        conn.close()


@bp.route("/categories", methods=["GET"])
@require_auth
def list_categories():
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT DISTINCT category FROM products WHERE category IS NOT NULL AND category != '' ORDER BY category"
        ).fetchall()
        return jsonify([r["category"] for r in rows])
    finally:
        conn.close()


@bp.route("/barcode/<code>", methods=["GET"])
@require_auth
def find_by_barcode(code):
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM products WHERE barcode = ? AND active = 1", (code,)
        ).fetchone()
        if not row:
            return jsonify({"error": "No product with that barcode."}), 404
        return jsonify(dict(row))
    finally:
        conn.close()


@bp.route("/<int:product_id>", methods=["GET"])
@require_auth
def get_product(product_id):
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
        if not row:
            return jsonify({"error": "Product not found."}), 404
        return jsonify(dict(row))
    finally:
        conn.close()


def _validate_product_payload(data, partial=False):
    errors = []
    if not partial or "sku" in data:
        if not (data.get("sku") or "").strip():
            errors.append("SKU is required.")
    if not partial or "name" in data:
        if not (data.get("name") or "").strip():
            errors.append("Name is required.")
    for numeric_field in ("cost_price", "sell_price", "reorder_point", "quantity_on_hand"):
        if numeric_field in data and data[numeric_field] is not None:
            try:
                float(data[numeric_field])
            except (TypeError, ValueError):
                errors.append(f"{numeric_field} must be a number.")
    return errors


@bp.route("", methods=["POST"])
@require_auth
@require_role("admin")
def create_product():
    data = request.get_json(silent=True) or {}
    errors = _validate_product_payload(data)
    if errors:
        return jsonify({"error": " ".join(errors)}), 400

    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT id FROM products WHERE sku = ?", (data["sku"].strip(),)
        ).fetchone()
        if existing:
            return jsonify({"error": "A product with that SKU already exists."}), 409

        barcode = (data.get("barcode") or "").strip() or None
        if barcode:
            dup = conn.execute("SELECT id FROM products WHERE barcode = ?", (barcode,)).fetchone()
            if dup:
                return jsonify({"error": "A product with that barcode already exists."}), 409

        created = now_str()
        cur = conn.execute(
            """INSERT INTO products
               (sku, barcode, name, description, category, unit, cost_price, sell_price,
                reorder_point, quantity_on_hand, default_supplier_id, active, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)""",
            (
                data["sku"].strip(),
                barcode,
                data["name"].strip(),
                data.get("description"),
                data.get("category"),
                data.get("unit") or "ea",
                float(data.get("cost_price") or 0),
                float(data.get("sell_price") or 0),
                int(data.get("reorder_point") or 0),
                int(data.get("quantity_on_hand") or 0),
                data.get("default_supplier_id"),
                created,
                created,
            ),
        )
        product_id = cur.lastrowid

        opening_qty = int(data.get("quantity_on_hand") or 0)
        if opening_qty:
            conn.execute(
                """INSERT INTO stock_transactions
                   (product_id, type, reason, quantity, resulting_quantity, reference, notes, created_by, created_at)
                   VALUES (?, 'in', 'adjustment', ?, ?, 'Opening balance', 'Initial stock when product was created', ?, ?)""",
                (product_id, opening_qty, opening_qty, g.user["id"], now_str()),
            )
        conn.commit()
        return jsonify({"id": product_id}), 201
    finally:
        conn.close()


@bp.route("/<int:product_id>", methods=["PATCH"])
@require_auth
@require_role("admin")
def update_product(product_id):
    data = request.get_json(silent=True) or {}
    errors = _validate_product_payload(data, partial=True)
    if errors:
        return jsonify({"error": " ".join(errors)}), 400

    conn = get_connection()
    try:
        product = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
        if not product:
            return jsonify({"error": "Product not found."}), 404

        editable = [
            "sku", "barcode", "name", "description", "category", "unit",
            "cost_price", "sell_price", "reorder_point", "default_supplier_id", "active",
        ]
        fields, params = [], []
        for f in editable:
            if f in data:
                fields.append(f"{f} = ?")
                params.append(data[f])
        if not fields:
            return jsonify({"error": "Nothing to update."}), 400

        fields.append("updated_at = ?")
        params.append(now_str())
        params.append(product_id)
        conn.execute(f"UPDATE products SET {', '.join(fields)} WHERE id = ?", params)
        conn.commit()
        return jsonify({"ok": True})
    finally:
        conn.close()


@bp.route("/<int:product_id>/transactions", methods=["GET"])
@require_auth
def product_transactions(product_id):
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT t.*, u.full_name AS created_by_name, c.name AS captain_name, tm.name AS team_name
               FROM stock_transactions t
               LEFT JOIN users u ON u.id = t.created_by
               LEFT JOIN captains c ON c.id = t.captain_id
               LEFT JOIN teams tm ON tm.id = t.team_id
               WHERE t.product_id = ?
               ORDER BY t.created_at DESC, t.id DESC
               LIMIT 200""",
            (product_id,),
        ).fetchall()
        return jsonify(rows_to_list(rows))
    finally:
        conn.close()
