import os
import tempfile
import pytest
from fastapi.testclient import TestClient

# Must set DB_PATH before importing app
_test_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_test_db.close()
os.environ["DB_PATH"] = _test_db.name

import database
from app import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    """Reset database before each test."""
    from database import init_db
    import sqlite3
    init_db()
    conn = sqlite3.connect(database.DB_PATH)
    conn.execute("DELETE FROM usage_log")
    conn.execute("DELETE FROM items")
    conn.commit()
    conn.close()
    yield


# --- Happy Path Tests ---

def test_create_and_get_item():
    """Happy path: create an item and retrieve it."""
    payload = {
        "name": "Organic Tea",
        "category": "Perishable",
        "quantity": 50,
        "unit": "bags",
        "expiry_date": "2026-06-01",
        "daily_usage_rate": 5.0,
        "cost_per_unit": 0.30,
        "supplier": "Tea Co",
        "is_eco_certified": True,
        "notes": "Green tea, fair trade",
    }
    res = client.post("/api/items", json=payload)
    assert res.status_code == 201
    data = res.json()
    assert data["name"] == "Organic Tea"
    assert data["quantity"] == 50
    assert data["is_eco_certified"] == 1
    item_id = data["id"]

    # Retrieve
    res2 = client.get(f"/api/items/{item_id}")
    assert res2.status_code == 200
    assert res2.json()["name"] == "Organic Tea"


def test_list_and_search_items():
    """Happy path: list items with search filter."""
    client.post("/api/items", json={"name": "Coffee Beans", "quantity": 10, "unit": "kg"})
    client.post("/api/items", json={"name": "Paper Cups", "quantity": 200, "unit": "pieces"})

    # List all
    res = client.get("/api/items")
    assert res.status_code == 200
    assert res.json()["count"] == 2

    # Search
    res2 = client.get("/api/items?search=coffee")
    assert res2.json()["count"] == 1
    assert res2.json()["items"][0]["name"] == "Coffee Beans"


def test_update_item():
    """Happy path: update an item's quantity."""
    res = client.post("/api/items", json={"name": "Milk", "quantity": 10, "unit": "liters"})
    item_id = res.json()["id"]

    res2 = client.put(f"/api/items/{item_id}", json={"quantity": 25})
    assert res2.status_code == 200
    assert res2.json()["quantity"] == 25


def test_prediction_fallback():
    """Happy path: prediction uses rule-based fallback."""
    res = client.post("/api/items", json={
        "name": "Sugar",
        "quantity": 20,
        "unit": "kg",
        "daily_usage_rate": 2.0,
    })
    item_id = res.json()["id"]

    pred = client.get(f"/api/items/{item_id}/predict")
    assert pred.status_code == 200
    data = pred.json()
    assert data["method"] == "rule-based"
    assert data["days_until_empty"] == 10
    assert data["urgency"] == "ok"


def test_sustainability_score():
    """Happy path: sustainability score calculates correctly."""
    client.post("/api/items", json={"name": "Eco Item", "quantity": 5, "unit": "pcs", "is_eco_certified": True})
    client.post("/api/items", json={"name": "Regular Item", "quantity": 5, "unit": "pcs", "is_eco_certified": False})

    res = client.get("/api/sustainability")
    assert res.status_code == 200
    data = res.json()
    assert data["eco_certified_pct"] == 50
    assert data["total_items"] == 2


# --- Edge Case Tests ---

def test_create_item_empty_name():
    """Edge case: reject item with empty name."""
    res = client.post("/api/items", json={"name": "", "quantity": 5, "unit": "pcs"})
    assert res.status_code == 422


def test_create_item_negative_quantity():
    """Edge case: reject negative quantity."""
    res = client.post("/api/items", json={"name": "Test", "quantity": -5, "unit": "pcs"})
    assert res.status_code == 422


def test_get_nonexistent_item():
    """Edge case: 404 for missing item."""
    res = client.get("/api/items/99999")
    assert res.status_code == 404


def test_delete_item():
    """Edge case: delete and verify gone."""
    res = client.post("/api/items", json={"name": "Temp", "quantity": 1, "unit": "pcs"})
    item_id = res.json()["id"]

    del_res = client.delete(f"/api/items/{item_id}")
    assert del_res.status_code == 200

    get_res = client.get(f"/api/items/{item_id}")
    assert get_res.status_code == 404


def test_usage_exceeds_stock():
    """Edge case: logging more usage than available stock."""
    res = client.post("/api/items", json={"name": "Limited", "quantity": 3, "unit": "pcs"})
    item_id = res.json()["id"]

    usage_res = client.post(f"/api/items/{item_id}/usage", json={"quantity_used": 10})
    assert usage_res.status_code == 400


def test_prediction_no_usage_rate():
    """Edge case: prediction when daily_usage_rate is 0."""
    res = client.post("/api/items", json={"name": "Static", "quantity": 100, "unit": "pcs", "daily_usage_rate": 0})
    item_id = res.json()["id"]

    pred = client.get(f"/api/items/{item_id}/predict")
    data = pred.json()
    assert data["days_until_empty"] is None
    assert data["urgency"] == "unknown"


def test_local_forecast_with_usage_history():
    """Happy path: local forecast uses exponential smoothing when enough usage data exists."""
    import sqlite3
    from datetime import datetime, timedelta

    res = client.post("/api/items", json={
        "name": "Forecast Coffee",
        "quantity": 50,
        "unit": "kg",
        "daily_usage_rate": 3.0,
    })
    item_id = res.json()["id"]

    # Insert 5 days of synthetic usage history directly into DB
    conn = sqlite3.connect(database.DB_PATH)
    base_date = datetime.now() - timedelta(days=5)
    for i in range(5):
        log_date = (base_date + timedelta(days=i)).strftime("%Y-%m-%d 10:00:00")
        conn.execute(
            "INSERT INTO usage_log (item_id, quantity_used, logged_at) VALUES (?, ?, ?)",
            (item_id, 2.0 + i * 0.5, log_date),  # increasing usage: 2.0, 2.5, 3.0, 3.5, 4.0
        )
    conn.commit()
    conn.close()

    pred = client.get(f"/api/items/{item_id}/predict")
    data = pred.json()
    assert data["method"] == "local-forecast"
    assert data["model"] == "holt-linear"
    assert data["days_until_empty"] is not None
    assert data["trend"] == "increasing"
    assert data["forecast_usage_rate"] > 0


def test_local_forecast_falls_back_without_history():
    """Edge case: forecast falls back to rule-based when no usage logs exist."""
    res = client.post("/api/items", json={
        "name": "New Item",
        "quantity": 30,
        "unit": "pcs",
        "daily_usage_rate": 5.0,
    })
    item_id = res.json()["id"]

    pred = client.get(f"/api/items/{item_id}/predict")
    data = pred.json()
    assert data["method"] == "rule-based"
    assert data["days_until_empty"] == 6
    assert "note" in data  # Should explain insufficient history


def test_what_if_reduce_usage():
    """Happy path: what-if simulator reduces usage and shows impact."""
    client.post("/api/items", json={
        "name": "Coffee",
        "quantity": 20,
        "unit": "kg",
        "daily_usage_rate": 3.0,
        "cost_per_unit": 18.0,
        "is_eco_certified": True,
        "expiry_date": "2026-03-20",
    })
    client.post("/api/items", json={
        "name": "Cups",
        "quantity": 100,
        "unit": "pcs",
        "daily_usage_rate": 20.0,
        "cost_per_unit": 0.10,
    })

    items = client.get("/api/items").json()["items"]
    coffee_id = next(i["id"] for i in items if i["name"] == "Coffee")

    res = client.post("/api/what-if", json={
        "action": "reduce_usage",
        "item_id": coffee_id,
        "reduce_pct": 50,
    })
    assert res.status_code == 200
    data = res.json()
    assert "baseline" in data
    assert "projected" in data
    assert "delta" in data
    assert data["projected"]["weekly_procurement_cost"] < data["baseline"]["weekly_procurement_cost"]


def test_what_if_invalid_action():
    """Edge case: what-if rejects unknown scenario action."""
    client.post("/api/items", json={"name": "X", "quantity": 1, "unit": "pcs"})
    items = client.get("/api/items").json()["items"]

    res = client.post("/api/what-if", json={
        "action": "teleport",
        "item_id": items[0]["id"],
    })
    assert res.status_code == 200
    assert "error" in res.json()


def test_chat_waste_query():
    """Happy path: chat co-pilot answers waste reduction question."""
    client.post("/api/items", json={
        "name": "Milk",
        "quantity": 50,
        "unit": "liters",
        "daily_usage_rate": 2.0,
        "cost_per_unit": 1.5,
        "expiry_date": "2026-03-20",
    })

    res = client.post("/api/chat", json={"query": "How can I reduce waste?"})
    assert res.status_code == 200
    data = res.json()
    assert "answer" in data
    assert "actions" in data


def test_chat_unknown_query():
    """Edge case: chat handles unrecognized queries gracefully."""
    res = client.post("/api/chat", json={"query": "What is the meaning of life?"})
    assert res.status_code == 200
    data = res.json()
    assert "suggestions" in data  # Should offer helpful suggestions


# --- Holt's Method & Seasonality Tests ---

def test_holt_trend_detection():
    """Holt's method detects increasing trend from rising usage data."""
    import sqlite3
    from datetime import datetime, timedelta

    res = client.post("/api/items", json={
        "name": "Trending Item",
        "quantity": 100,
        "unit": "kg",
        "daily_usage_rate": 3.0,
    })
    item_id = res.json()["id"]

    conn = sqlite3.connect(database.DB_PATH)
    base_date = datetime.now() - timedelta(days=7)
    for i in range(7):
        log_date = (base_date + timedelta(days=i)).strftime("%Y-%m-%d 10:00:00")
        conn.execute(
            "INSERT INTO usage_log (item_id, quantity_used, logged_at) VALUES (?, ?, ?)",
            (item_id, 2.0 + i * 1.0, log_date),  # 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0
        )
    conn.commit()
    conn.close()

    pred = client.get(f"/api/items/{item_id}/predict")
    data = pred.json()
    assert data["trend"] == "increasing"
    assert data["trend_per_day"] > 0


def test_holt_stable_trend():
    """Holt's method reports stable trend for flat usage data."""
    import sqlite3
    from datetime import datetime, timedelta

    res = client.post("/api/items", json={
        "name": "Flat Item",
        "quantity": 100,
        "unit": "kg",
        "daily_usage_rate": 5.0,
    })
    item_id = res.json()["id"]

    conn = sqlite3.connect(database.DB_PATH)
    base_date = datetime.now() - timedelta(days=7)
    for i in range(7):
        log_date = (base_date + timedelta(days=i)).strftime("%Y-%m-%d 10:00:00")
        conn.execute(
            "INSERT INTO usage_log (item_id, quantity_used, logged_at) VALUES (?, ?, ?)",
            (item_id, 5.0, log_date),
        )
    conn.commit()
    conn.close()

    pred = client.get(f"/api/items/{item_id}/predict")
    data = pred.json()
    assert data["trend"] == "stable"
    assert abs(data["trend_per_day"]) < 0.5


def test_seasonality_detected_with_weekly_pattern():
    """Seasonality is detected when weekends differ significantly from weekdays."""
    import sqlite3
    from datetime import datetime, timedelta

    res = client.post("/api/items", json={
        "name": "Seasonal Item",
        "quantity": 200,
        "unit": "pcs",
        "daily_usage_rate": 7.0,
    })
    item_id = res.json()["id"]

    conn = sqlite3.connect(database.DB_PATH)
    base_date = datetime.now() - timedelta(days=14)
    for i in range(14):
        log_date = base_date + timedelta(days=i)
        weekday = log_date.weekday()
        usage = 10.0 if weekday >= 5 else 5.0  # weekend=10, weekday=5
        conn.execute(
            "INSERT INTO usage_log (item_id, quantity_used, logged_at) VALUES (?, ?, ?)",
            (item_id, usage, log_date.strftime("%Y-%m-%d 10:00:00")),
        )
    conn.commit()
    conn.close()

    pred = client.get(f"/api/items/{item_id}/predict")
    data = pred.json()
    assert data["seasonality"]["detected"] is True
    assert data["seasonality"]["peak_day"] in ("Sat", "Sun")


def test_seasonality_not_detected_uniform():
    """Seasonality is not detected when usage is uniform across all days."""
    import sqlite3
    from datetime import datetime, timedelta

    res = client.post("/api/items", json={
        "name": "Uniform Item",
        "quantity": 100,
        "unit": "pcs",
        "daily_usage_rate": 3.0,
    })
    item_id = res.json()["id"]

    conn = sqlite3.connect(database.DB_PATH)
    base_date = datetime.now() - timedelta(days=14)
    for i in range(14):
        log_date = (base_date + timedelta(days=i)).strftime("%Y-%m-%d 10:00:00")
        conn.execute(
            "INSERT INTO usage_log (item_id, quantity_used, logged_at) VALUES (?, ?, ?)",
            (item_id, 3.0, log_date),
        )
    conn.commit()
    conn.close()

    pred = client.get(f"/api/items/{item_id}/predict")
    data = pred.json()
    assert data["seasonality"]["detected"] is False


def test_confidence_field_present():
    """Confidence field is present and 'low' with only 5 days of data."""
    import sqlite3
    from datetime import datetime, timedelta

    res = client.post("/api/items", json={
        "name": "Short History Item",
        "quantity": 50,
        "unit": "pcs",
        "daily_usage_rate": 2.0,
    })
    item_id = res.json()["id"]

    conn = sqlite3.connect(database.DB_PATH)
    base_date = datetime.now() - timedelta(days=5)
    for i in range(5):
        log_date = (base_date + timedelta(days=i)).strftime("%Y-%m-%d 10:00:00")
        conn.execute(
            "INSERT INTO usage_log (item_id, quantity_used, logged_at) VALUES (?, ?, ?)",
            (item_id, 2.0, log_date),
        )
    conn.commit()
    conn.close()

    pred = client.get(f"/api/items/{item_id}/predict")
    data = pred.json()
    assert "confidence" in data
    assert data["confidence"] in ("low", "medium")


# --- Shelf Life Prediction Tests ---

def test_shelf_life_in_prediction():
    """Shelf life prediction is included in prediction response."""
    res = client.post("/api/items", json={
        "name": "Milk",
        "quantity": 10,
        "unit": "liters",
        "daily_usage_rate": 3.0,
        "expiry_date": "2026-04-01",
        "category": "Perishable",
        "storage_condition": "refrigerated",
    })
    item_id = res.json()["id"]
    pred = client.get(f"/api/items/{item_id}/predict")
    data = pred.json()
    assert "shelf_life" in data
    assert data["shelf_life"]["effective_shelf_life_days"] >= 0
    assert "factors" in data["shelf_life"]
    assert data["shelf_life"]["factors"]["storage_condition"] == "refrigerated"


def test_shelf_life_room_temp_perishable_shorter():
    """Room temp perishable has shorter effective shelf life than nominal."""
    res = client.post("/api/items", json={
        "name": "Warm Milk",
        "quantity": 10,
        "unit": "liters",
        "daily_usage_rate": 5.0,
        "expiry_date": "2026-04-15",
        "category": "Perishable",
        "storage_condition": "room_temp",
    })
    item_id = res.json()["id"]
    pred = client.get(f"/api/items/{item_id}/predict")
    sl = pred.json()["shelf_life"]
    assert sl["effective_shelf_life_days"] < sl["nominal_expiry_days"]


# --- Sustainable Alternatives Tests ---

def test_sustainability_includes_alternatives():
    """Sustainability endpoint includes alternatives for non-eco items."""
    client.post("/api/items", json={
        "name": "Whole Milk",
        "quantity": 10,
        "unit": "liters",
        "is_eco_certified": False,
    })
    res = client.get("/api/sustainability")
    data = res.json()
    assert "alternatives_available" in data
    assert len(data["alternatives_available"]) > 0
    assert data["alternatives_available"][0]["item_name"] == "Whole Milk"


def test_create_item_with_storage_condition():
    """Items can be created with storage_condition field."""
    res = client.post("/api/items", json={
        "name": "Ice Cream",
        "quantity": 5,
        "unit": "tubs",
        "storage_condition": "frozen",
    })
    assert res.status_code == 201
    data = res.json()
    assert data["storage_condition"] == "frozen"


def test_chat_sustainability_shows_alternatives():
    """Chat sustainability response includes alternative_details."""
    client.post("/api/items", json={
        "name": "Whole Milk",
        "quantity": 10,
        "unit": "liters",
        "is_eco_certified": False,
    })
    res = client.post("/api/chat", json={"query": "How can I improve sustainability?"})
    data = res.json()
    assert "alternative_details" in data
    assert len(data["alternative_details"]) > 0


# --- Fuzzy Matching Tests ---

def test_alternatives_fuzzy_match_case_insensitive():
    """Alternatives match case-insensitively."""
    client.post("/api/items", json={"name": "whole milk", "quantity": 10, "unit": "liters", "is_eco_certified": False})
    res = client.get("/api/sustainability")
    assert len(res.json()["alternatives_available"]) > 0


def test_alternatives_fuzzy_match_partial():
    """Alternatives match partial names like 'Lab Gloves' -> 'Lab Gloves (Nitrile)'."""
    client.post("/api/items", json={"name": "Lab Gloves", "quantity": 50, "unit": "pairs", "is_eco_certified": False})
    res = client.get("/api/sustainability")
    assert len(res.json()["alternatives_available"]) > 0


def test_alternatives_show_score_improvement():
    """Switching a non-eco item to eco shows projected score improvement."""
    client.post("/api/items", json={"name": "Whole Milk", "quantity": 10, "unit": "liters", "is_eco_certified": False})
    client.post("/api/items", json={"name": "Eco Tea", "quantity": 10, "unit": "bags", "is_eco_certified": True})
    res = client.get("/api/sustainability")
    data = res.json()
    assert len(data["alternatives_available"]) > 0
    alt = data["alternatives_available"][0]
    assert "projected_score" in alt
    assert "score_improvement" in alt
    assert alt["projected_score"] > data["overall_score"]
    assert alt["score_improvement"] > 0


def test_alternatives_no_false_positive():
    """Unrelated items don't falsely match alternatives."""
    client.post("/api/items", json={"name": "Printer Ink", "quantity": 5, "unit": "cartridges", "is_eco_certified": False})
    res = client.get("/api/sustainability")
    assert len(res.json()["alternatives_available"]) == 0


# --- Forecast Cache Tests ---

def test_forecast_cache_hit():
    """Second prediction call uses cached forecast (same result)."""
    import sqlite3
    from datetime import datetime, timedelta

    res = client.post("/api/items", json={"name": "CacheTea", "quantity": 50, "unit": "bags", "daily_usage_rate": 5.0})
    item_id = res.json()["id"]
    conn = sqlite3.connect(database.DB_PATH)
    base_date = datetime.now() - timedelta(days=5)
    for i in range(5):
        log_date = (base_date + timedelta(days=i)).strftime("%Y-%m-%d 10:00:00")
        conn.execute("INSERT INTO usage_log (item_id, quantity_used, logged_at) VALUES (?, ?, ?)", (item_id, 5.0, log_date))
    conn.commit()
    conn.close()
    pred1 = client.get(f"/api/items/{item_id}/predict").json()
    pred2 = client.get(f"/api/items/{item_id}/predict").json()
    assert pred1["forecast_usage_rate"] == pred2["forecast_usage_rate"]
    assert pred1["method"] == "local-forecast"


def test_forecast_cache_invalidated_on_usage():
    """Cache is invalidated when new usage is logged."""
    import sqlite3
    from datetime import datetime, timedelta

    res = client.post("/api/items", json={"name": "CacheMilk", "quantity": 50, "unit": "liters", "daily_usage_rate": 3.0})
    item_id = res.json()["id"]
    conn = sqlite3.connect(database.DB_PATH)
    base_date = datetime.now() - timedelta(days=5)
    for i in range(5):
        log_date = (base_date + timedelta(days=i)).strftime("%Y-%m-%d 10:00:00")
        conn.execute("INSERT INTO usage_log (item_id, quantity_used, logged_at) VALUES (?, ?, ?)", (item_id, 3.0, log_date))
    conn.commit()
    conn.close()
    pred1 = client.get(f"/api/items/{item_id}/predict").json()
    client.post(f"/api/items/{item_id}/usage", json={"quantity_used": 10.0})
    pred2 = client.get(f"/api/items/{item_id}/predict").json()
    assert pred2["days_until_empty"] < pred1["days_until_empty"]
