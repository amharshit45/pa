import sqlite3
import json
import os
from contextlib import contextmanager

DB_PATH = os.getenv("DB_PATH", "inventory.db")


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'Supplies',
                quantity REAL NOT NULL DEFAULT 0,
                unit TEXT NOT NULL DEFAULT 'pieces',
                expiry_date TEXT,
                daily_usage_rate REAL DEFAULT 0,
                cost_per_unit REAL DEFAULT 0,
                supplier TEXT DEFAULT '',
                is_eco_certified INTEGER DEFAULT 0,
                storage_condition TEXT DEFAULT 'room_temp',
                notes TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS usage_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER NOT NULL,
                quantity_used REAL NOT NULL,
                logged_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (item_id) REFERENCES items(id)
            )
        """)


def seed_from_json(path="data/sample_data.json"):
    with get_db() as conn:
        count = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
        if count > 0:
            return
        with open(path) as f:
            items = json.load(f)
        for item in items:
            conn.execute(
                """INSERT INTO items (name, category, quantity, unit, expiry_date,
                   daily_usage_rate, cost_per_unit, supplier, is_eco_certified,
                   storage_condition, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    item["name"], item["category"], item["quantity"], item["unit"],
                    item.get("expiry_date"), item.get("daily_usage_rate", 0),
                    item.get("cost_per_unit", 0), item.get("supplier", ""),
                    1 if item.get("is_eco_certified") else 0,
                    item.get("storage_condition", "room_temp"),
                    item.get("notes", ""),
                ),
            )
        _seed_usage_logs(conn)


def _seed_usage_logs(conn):
    """Load pre-generated usage history from static JSON file.

    The data was generated with the same seasonal/trend/variance logic
    previously in this function, anchored to 2026-03-20 for stability.
    """
    path = os.path.join(os.path.dirname(__file__), "data", "sample_usage_logs.json")
    if not os.path.exists(path):
        return
    with open(path) as f:
        logs = json.load(f)
    for log in logs:
        conn.execute(
            "INSERT INTO usage_log (item_id, quantity_used, logged_at) VALUES (?, ?, ?)",
            (log["item_id"], log["quantity_used"], log["logged_at"]),
        )
