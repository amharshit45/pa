"""Inventory Service - CRUD operations, search, and usage logging."""

from database import get_db
from services.prediction_engine import rule_based_prediction, invalidate_forecast_cache


def list_items(search: str = "", category: str = "", urgency: str = "") -> dict:
    with get_db() as conn:
        query = "SELECT * FROM items WHERE 1=1"
        params = []
        if search:
            query += " AND (name LIKE ? OR supplier LIKE ?)"
            params += [f"%{search}%", f"%{search}%"]
        if category:
            query += " AND category = ?"
            params.append(category)
        query += " ORDER BY name"
        rows = conn.execute(query, params).fetchall()
        items = [dict(r) for r in rows]

    if urgency:
        items = [i for i in items if rule_based_prediction(i).get("urgency") == urgency]

    return {"items": items, "count": len(items)}


def get_item(item_id: int) -> dict:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    return dict(row) if row else None


def create_item(data: dict) -> dict:
    with get_db() as conn:
        cursor = conn.execute(
            """INSERT INTO items (name, category, quantity, unit, expiry_date,
               daily_usage_rate, cost_per_unit, supplier, is_eco_certified,
               storage_condition, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                data["name"], data.get("category", "Supplies"), data["quantity"],
                data.get("unit", "pieces"), data.get("expiry_date"),
                data.get("daily_usage_rate", 0), data.get("cost_per_unit", 0),
                data.get("supplier", ""), 1 if data.get("is_eco_certified") else 0,
                data.get("storage_condition", "room_temp"),
                data.get("notes", ""),
            ),
        )
        row = conn.execute("SELECT * FROM items WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return dict(row)


def update_item(item_id: int, fields: dict) -> dict:
    with get_db() as conn:
        existing = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
        if not existing:
            return None
        if "is_eco_certified" in fields:
            fields["is_eco_certified"] = 1 if fields["is_eco_certified"] else 0
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [item_id]
        conn.execute(
            f"UPDATE items SET {set_clause}, updated_at = datetime('now') WHERE id = ?",
            values,
        )
        row = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    return dict(row)


def delete_item(item_id: int) -> bool:
    with get_db() as conn:
        existing = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
        if not existing:
            return False
        conn.execute("DELETE FROM items WHERE id = ?", (item_id,))
    invalidate_forecast_cache(item_id)
    return True


def log_usage(item_id: int, quantity_used: float) -> dict:
    """Log usage and decrement stock. Returns updated item or error dict."""
    with get_db() as conn:
        item = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
        if not item:
            return {"error": "not_found"}
        new_qty = item["quantity"] - quantity_used
        if new_qty < 0:
            return {"error": "insufficient_stock", "current": item["quantity"], "unit": item["unit"]}
        conn.execute("UPDATE items SET quantity = ?, updated_at = datetime('now') WHERE id = ?", (new_qty, item_id))
        conn.execute("INSERT INTO usage_log (item_id, quantity_used) VALUES (?, ?)", (item_id, quantity_used))
        row = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    invalidate_forecast_cache(item_id)
    return dict(row)


def get_all_items() -> list:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM items ORDER BY name").fetchall()
    return [dict(r) for r in rows]


def get_categories() -> list:
    with get_db() as conn:
        rows = conn.execute("SELECT DISTINCT category FROM items ORDER BY category").fetchall()
    return [r["category"] for r in rows]
