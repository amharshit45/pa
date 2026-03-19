import sqlite3
import json
import os
import random
from contextlib import contextmanager
from datetime import datetime, timedelta

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
                   daily_usage_rate, cost_per_unit, supplier, is_eco_certified, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    item["name"], item["category"], item["quantity"], item["unit"],
                    item.get("expiry_date"), item.get("daily_usage_rate", 0),
                    item.get("cost_per_unit", 0), item.get("supplier", ""),
                    1 if item.get("is_eco_certified") else 0, item.get("notes", ""),
                ),
            )
        _seed_usage_logs(conn)


def _seed_usage_logs(conn):
    """Generate 60 days (2 months) of synthetic usage history for each item.

    Adds realistic variance around each item's daily_usage_rate with
    day-of-week seasonal multipliers so the prediction engine can
    detect weekly patterns with high confidence. Perishable items spike
    on weekends; Supplies/Equipment items spike on weekdays.
    """
    SEED_DAYS = 60  # 2 months of history

    # Day-of-week seasonal multipliers (0=Mon, 6=Sun)
    WEEKEND_SEASONAL = {0: 0.90, 1: 0.85, 2: 0.90, 3: 0.95, 4: 1.10, 5: 1.25, 6: 1.05}
    WEEKDAY_SEASONAL = {0: 1.10, 1: 1.10, 2: 1.05, 3: 1.05, 4: 1.00, 5: 0.85, 6: 0.85}

    items = conn.execute("SELECT id, daily_usage_rate, category FROM items").fetchall()
    now = datetime.now()
    random.seed(42)  # reproducible demo data
    for item in items:
        rate = item[1]
        category = item[2] if len(item) > 2 else "Supplies"
        if rate <= 0:
            continue
        seasonal = WEEKEND_SEASONAL if category == "Perishable" else WEEKDAY_SEASONAL
        for day_offset in range(SEED_DAYS, 0, -1):
            log_date = now - timedelta(days=day_offset)
            weekday = log_date.weekday()
            # Apply seasonal multiplier, gentle trend, and +/- 20% variance
            trend_factor = 1.0 + (SEED_DAYS - day_offset) * 0.002  # up to +12% over 60 days
            season_factor = seasonal.get(weekday, 1.0)
            usage = max(0.1, rate * trend_factor * season_factor * random.uniform(0.8, 1.2))
            conn.execute(
                "INSERT INTO usage_log (item_id, quantity_used, logged_at) VALUES (?, ?, ?)",
                (item[0], round(usage, 2), log_date.strftime("%Y-%m-%d %H:%M:%S")),
            )
