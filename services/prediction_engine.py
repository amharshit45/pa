"""Prediction Engine - Local ML forecasting with rule-based fallback."""

import math
import statistics
from typing import Optional
from datetime import datetime, timedelta
from database import get_db

DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# Shelf life prediction constants
CATEGORY_SHELF_LIFE = {"Perishable": 7, "Supplies": 365, "Equipment": 730}
STORAGE_MULTIPLIERS = {"frozen": 3.0, "refrigerated": 1.0, "room_temp": 0.6, "warm": 0.3}
STORAGE_MULTIPLIERS_NON_PERISHABLE = {"frozen": 1.0, "refrigerated": 1.0, "room_temp": 1.0, "warm": 0.9}

# Forecast cache: {item_id: {"forecast": dict, "usage_count": int}}
_forecast_cache = {}


def invalidate_forecast_cache(item_id: int = None):
    """Clear cached forecast for an item, or all items if item_id is None."""
    if item_id is None:
        _forecast_cache.clear()
    else:
        _forecast_cache.pop(item_id, None)


def rule_based_prediction(item: dict) -> dict:
    """Simple math-based prediction using quantity / daily_usage_rate."""
    quantity = item.get("quantity", 0)
    rate = item.get("daily_usage_rate", 0)
    expiry = item.get("expiry_date")
    name = item.get("name", "Item")

    result = {"item": name, "method": "rule-based"}

    if rate > 0:
        days_left = math.floor(quantity / rate)
        runout_date = datetime.now() + timedelta(days=days_left)
        result["days_until_empty"] = days_left
        result["estimated_runout"] = runout_date.strftime("%Y-%m-%d")
        result["urgency"] = "critical" if days_left <= 2 else "warning" if days_left <= 7 else "ok"
        result["recommendation"] = (
            f"Reorder soon! Only ~{days_left} days of supply left at current usage."
            if days_left <= 7
            else f"Sufficient stock for ~{days_left} days."
        )
    else:
        result["days_until_empty"] = None
        result["recommendation"] = "No usage rate recorded. Set a daily usage rate for predictions."
        result["urgency"] = "unknown"

    _apply_expiry_check(result, expiry)
    _apply_sustainability_tip(result, item)
    result["shelf_life"] = predict_shelf_life(item)

    return result


def holt_forecast(usage_history: list) -> Optional[dict]:
    """
    Forecast daily usage rate using Holt's double exponential smoothing (level + trend).

    Groups usage logs by date, applies smoothing to produce a rate that
    weights recent data more heavily and explicitly tracks trend.
    Returns None if insufficient data (<3 daily data points).
    """
    if len(usage_history) < 3:
        return None

    daily_usage = {}
    date_weekdays = {}
    for log in usage_history:
        date_str = log["logged_at"][:10]
        daily_usage[date_str] = daily_usage.get(date_str, 0) + log["quantity_used"]
        date_weekdays[date_str] = datetime.strptime(date_str, "%Y-%m-%d").weekday()

    dates_sorted = sorted(daily_usage.keys())
    if len(dates_sorted) < 3:
        return None

    start = datetime.strptime(dates_sorted[0], "%Y-%m-%d")
    end = datetime.strptime(dates_sorted[-1], "%Y-%m-%d")
    all_days = []
    all_weekdays = []
    current = start
    while current <= end:
        day_str = current.strftime("%Y-%m-%d")
        all_days.append(daily_usage.get(day_str, 0))
        all_weekdays.append(current.weekday())
        current += timedelta(days=1)

    if len(all_days) < 3:
        return None

    # Holt's double exponential smoothing
    alpha = 0.3
    beta = 0.1

    L = all_days[0]
    T = (all_days[min(2, len(all_days) - 1)] - all_days[0]) / 2

    fitted = [L + T]
    for val in all_days[1:]:
        L_prev = L
        L = alpha * val + (1 - alpha) * (L + T)
        T = beta * (L - L_prev) + (1 - beta) * T
        fitted.append(L + T)

    # MAE from in-sample fitted values
    errors = [abs(all_days[i] - fitted[i]) for i in range(len(all_days))]
    mae = sum(errors) / len(errors)

    smoothed_rate = L + T
    trend_pct = (T / L * 100) if L > 0 else 0

    # Seasonality detection
    seasonality = detect_weekly_seasonality(all_days, all_weekdays)

    # Confidence
    overall_mean = sum(all_days) / len(all_days) if all_days else 1
    confidence = compute_confidence(len(all_days), mae, overall_mean)

    return {
        "smoothed_rate": round(max(smoothed_rate, 0), 2),
        "trend_pct": round(trend_pct, 1),
        "trend_per_day": round(T, 4),
        "data_points": len(all_days),
        "date_range": f"{dates_sorted[0]} to {dates_sorted[-1]}",
        "seasonality": seasonality,
        "confidence": confidence,
        "mae": round(mae, 2),
    }


def detect_weekly_seasonality(values: list, weekdays: list) -> dict:
    """Detect day-of-week seasonal patterns in usage data."""
    if len(values) < 7:
        return {"detected": False}

    # Group values by weekday
    by_weekday = {}
    for val, wd in zip(values, weekdays):
        by_weekday.setdefault(wd, []).append(val)

    overall_mean = sum(values) / len(values) if values else 1
    if overall_mean == 0:
        return {"detected": False}

    indices = {}
    for wd in range(7):
        if wd in by_weekday and by_weekday[wd]:
            wd_mean = sum(by_weekday[wd]) / len(by_weekday[wd])
            indices[DAY_NAMES[wd]] = round(wd_mean / overall_mean, 2)
        else:
            indices[DAY_NAMES[wd]] = 1.0

    index_values = list(indices.values())
    stdev = statistics.stdev(index_values) if len(index_values) > 1 else 0

    detected = stdev > 0.10

    peak_day = max(indices, key=indices.get)
    trough_day = min(indices, key=indices.get)
    peak_mult = indices[peak_day]
    trough_mult = indices[trough_day]

    # Confidence based on data span
    if len(values) >= 28:
        seas_confidence = "high"
    elif len(values) >= 14:
        seas_confidence = "medium"
    else:
        seas_confidence = "low"

    peak_pct = round((peak_mult - 1) * 100)
    trough_pct = round((trough_mult - 1) * 100)
    description = (
        f"Usage peaks on {peak_day} ({'+' if peak_pct >= 0 else ''}{peak_pct}%), "
        f"dips on {trough_day} ({'+' if trough_pct >= 0 else ''}{trough_pct}%)"
    ) if detected else "No significant weekly pattern detected"

    return {
        "detected": detected,
        "indices": indices,
        "peak_day": peak_day,
        "trough_day": trough_day,
        "peak_multiplier": peak_mult,
        "confidence": seas_confidence,
        "description": description,
    }


def compute_confidence(data_points: int, mae: float, mean: float) -> str:
    """Heuristic confidence based on data quantity and fit quality."""
    if data_points < 7:
        base = 0
    elif data_points < 21:
        base = 1
    else:
        base = 2

    mae_pct = (mae / mean * 100) if mean > 0 else 100
    if mae_pct < 15:
        base += 1
    elif mae_pct > 30:
        base -= 1

    if base <= 0:
        return "low"
    elif base == 1:
        return "medium"
    else:
        return "high"


def local_forecast_prediction(item: dict) -> dict:
    """
    Primary prediction using local Holt's linear trend model.

    Falls back to rule-based when insufficient usage history exists.
    """
    item_id = item.get("id")
    name = item.get("name", "Item")
    quantity = item.get("quantity", 0)
    expiry = item.get("expiry_date")

    usage_history = []
    if item_id:
        try:
            with get_db() as conn:
                rows = conn.execute(
                    "SELECT quantity_used, logged_at FROM usage_log WHERE item_id = ? ORDER BY logged_at",
                    (item_id,),
                ).fetchall()
                usage_history = [dict(r) for r in rows]
        except Exception:
            pass

    # Check forecast cache: hit if same item_id and same number of usage records
    usage_count = len(usage_history)
    cached = _forecast_cache.get(item_id) if item_id else None
    if cached and cached["usage_count"] == usage_count:
        forecast = cached["forecast"]
    else:
        forecast = holt_forecast(usage_history)
        if forecast is not None and item_id:
            _forecast_cache[item_id] = {"forecast": forecast, "usage_count": usage_count}

    if forecast is None:
        fallback = rule_based_prediction(item)
        fallback["note"] = "Insufficient usage history for forecasting. Log more usage to enable trend-based predictions."
        return fallback

    smoothed_rate = forecast["smoothed_rate"]
    result = {
        "item": name,
        "method": "local-forecast",
        "model": "holt-linear",
        "forecast_usage_rate": smoothed_rate,
        "configured_usage_rate": item.get("daily_usage_rate", 0),
        "trend": (
            "increasing" if forecast["trend_pct"] > 10
            else "decreasing" if forecast["trend_pct"] < -10
            else "stable"
        ),
        "trend_pct": forecast["trend_pct"],
        "trend_per_day": forecast["trend_per_day"],
        "data_points": forecast["data_points"],
        "date_range": forecast["date_range"],
        "seasonality": forecast["seasonality"],
        "confidence": forecast["confidence"],
    }

    if smoothed_rate > 0:
        days_left = math.floor(quantity / smoothed_rate)
        runout_date = datetime.now() + timedelta(days=days_left)
        result["days_until_empty"] = days_left
        result["estimated_runout"] = runout_date.strftime("%Y-%m-%d")
        result["urgency"] = "critical" if days_left <= 2 else "warning" if days_left <= 7 else "ok"

        trend_note = ""
        if forecast["trend_pct"] > 10:
            trend_note = f" Usage is trending up ({forecast['trend_pct']}%), so you may run out sooner."
        elif forecast["trend_pct"] < -10:
            trend_note = f" Usage is trending down ({forecast['trend_pct']}%), supply may last longer."

        seasonality_note = ""
        if forecast["seasonality"].get("detected"):
            s = forecast["seasonality"]
            seasonality_note = f" Weekly pattern: {s['description']}."

        result["recommendation"] = (
            f"Based on {forecast['data_points']} days of usage data, "
            f"estimated ~{days_left} days of supply remaining.{trend_note}{seasonality_note}"
        )
    else:
        result["days_until_empty"] = None
        result["urgency"] = "ok"
        result["recommendation"] = "Usage has dropped to near zero based on recent history."

    _apply_expiry_check(result, expiry)
    _apply_sustainability_tip(result, item)
    result["shelf_life"] = predict_shelf_life(item)

    return result


def predict_all(items: list) -> dict:
    predictions = [local_forecast_prediction(i) for i in items]
    critical = [p for p in predictions if p.get("urgency") == "critical"]
    warnings = [p for p in predictions if p.get("urgency") == "warning"]
    return {"predictions": predictions, "critical_count": len(critical), "warning_count": len(warnings)}


def predict_shelf_life(item: dict) -> dict:
    """Predict effective shelf life factoring in storage conditions and handling frequency."""
    category = item.get("category", "Supplies")
    storage = item.get("storage_condition", "room_temp")
    expiry = item.get("expiry_date")
    rate = item.get("daily_usage_rate", 0)
    quantity = item.get("quantity", 0)

    if expiry:
        try:
            nominal_days = (datetime.strptime(expiry, "%Y-%m-%d") - datetime.now()).days
        except ValueError:
            nominal_days = CATEGORY_SHELF_LIFE.get(category, 365)
    else:
        nominal_days = CATEGORY_SHELF_LIFE.get(category, 365)

    base_shelf = max(nominal_days, 0)

    if category == "Perishable":
        storage_mult = STORAGE_MULTIPLIERS.get(storage, 1.0)
    else:
        storage_mult = STORAGE_MULTIPLIERS_NON_PERISHABLE.get(storage, 1.0)

    handling_factor = 1.0
    if category == "Perishable" and rate > 0 and quantity > 0:
        access_ratio = min(rate / quantity, 1.0)
        handling_factor = max(0.7, 1.0 - access_ratio * 0.3)

    effective_days = max(0, round(base_shelf * storage_mult * handling_factor))

    factors = {
        "base_shelf_life_days": base_shelf,
        "storage_condition": storage,
        "storage_multiplier": storage_mult,
        "handling_frequency_factor": round(handling_factor, 2),
        "category": category,
    }

    if effective_days <= 0:
        recommendation = "Item has no remaining effective shelf life. Use or discard immediately."
    elif effective_days <= 3:
        recommendation = f"Effective shelf life is only ~{effective_days} days due to storage/handling conditions. Prioritize use."
    elif expiry and effective_days < nominal_days:
        storage_advice = "refrigerating" if storage == "room_temp" and category == "Perishable" else "improving storage"
        recommendation = (
            f"Storage conditions reduce effective shelf life from {nominal_days} to ~{effective_days} days. "
            f"Consider {storage_advice}."
        )
    else:
        recommendation = f"Effective shelf life: ~{effective_days} days. Conditions are appropriate."

    return {
        "nominal_expiry_days": nominal_days if expiry else None,
        "effective_shelf_life_days": effective_days,
        "difference_days": effective_days - (nominal_days if nominal_days > 0 else base_shelf),
        "factors": factors,
        "recommendation": recommendation,
    }


def _apply_expiry_check(result: dict, expiry: Optional[str]):
    if not expiry:
        return
    try:
        exp_date = datetime.strptime(expiry, "%Y-%m-%d")
        days_to_expiry = (exp_date - datetime.now()).days
        result["days_until_expiry"] = days_to_expiry
        if days_to_expiry < 0:
            result["expiry_warning"] = "EXPIRED - remove from inventory immediately."
            result["urgency"] = "critical"
        elif days_to_expiry <= 3:
            result["expiry_warning"] = f"Expires in {days_to_expiry} days - use or donate soon."
            result["urgency"] = "critical"
        elif days_to_expiry <= 7:
            result["expiry_warning"] = f"Expires in {days_to_expiry} days - plan to use."
            if result.get("urgency") != "critical":
                result["urgency"] = "warning"
    except ValueError:
        pass


def _apply_sustainability_tip(result: dict, item: dict):
    if not item.get("is_eco_certified"):
        result["sustainability_tip"] = (
            f"Consider switching '{item.get('name', 'this item')}' to an eco-certified alternative "
            f"to reduce environmental impact."
        )
