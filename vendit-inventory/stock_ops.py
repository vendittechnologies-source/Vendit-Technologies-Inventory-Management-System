"""Shared helpers for recording stock movements consistently.

Every change to products.quantity_on_hand must go through here so that
stock_transactions stays a complete, reliable audit trail.
"""
from utils import ApiError, now_str


def apply_stock_change(
    conn,
    product_id,
    direction,  # 'in' or 'out'
    quantity,
    reason,
    created_by,
    captain_id=None,
    team_id=None,
    purchase_order_id=None,
    captain_run_id=None,
    reference=None,
    notes=None,
    allow_negative=False,
):
    if quantity is None or quantity <= 0:
        raise ApiError("Quantity must be a positive number.")
    if direction not in ("in", "out"):
        raise ApiError("Invalid stock movement direction.")

    product = conn.execute(
        "SELECT * FROM products WHERE id = ?", (product_id,)
    ).fetchone()
    if not product:
        raise ApiError(f"Product #{product_id} not found.", 404)

    if direction == "in":
        new_qty = product["quantity_on_hand"] + quantity
    else:
        new_qty = product["quantity_on_hand"] - quantity
        if new_qty < 0 and not allow_negative:
            raise ApiError(
                f"Not enough stock of '{product['name']}' (have {product['quantity_on_hand']}, "
                f"tried to remove {quantity})."
            )

    conn.execute(
        "UPDATE products SET quantity_on_hand = ?, updated_at = ? WHERE id = ?",
        (new_qty, now_str(), product_id),
    )
    conn.execute(
        """INSERT INTO stock_transactions
           (product_id, type, reason, quantity, resulting_quantity, captain_id, team_id,
            purchase_order_id, captain_run_id, reference, notes, created_by, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            product_id, direction, reason, quantity, new_qty, captain_id, team_id,
            purchase_order_id, captain_run_id, reference, notes, created_by, now_str(),
        ),
    )
    return new_qty
