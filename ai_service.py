import os
import math
from typing import Optional
from datetime import datetime, timedelta
from database import get_db


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

    return result


def _exponential_smoothing_forecast(usage_history: list) -> Optional[dict]:
    """
    Forecast daily usage rate using simple exponential smoothing on usage logs.

    Groups usage logs by date, applies exponential smoothing (alpha=0.3) to
    produce a smoothed daily usage rate that weights recent data more heavily.

    Returns None if insufficient data (<3 daily data points).
    """
    if len(usage_history) < 3:
        return None

    # Group usage by date
    daily_usage = {}
    for log in usage_history:
        date_str = log["logged_at"][:10]  # Extract YYYY-MM-DD
        daily_usage[date_str] = daily_usage.get(date_str, 0) + log["quantity_used"]

    dates_sorted = sorted(daily_usage.keys())
    if len(dates_sorted) < 3:
        return None

    # Fill in zero-usage days between first and last recorded date
    start = datetime.strptime(dates_sorted[0], "%Y-%m-%d")
    end = datetime.strptime(dates_sorted[-1], "%Y-%m-%d")
    all_days = []
    current = start
    while current <= end:
        day_str = current.strftime("%Y-%m-%d")
        all_days.append(daily_usage.get(day_str, 0))
        current += timedelta(days=1)

    if len(all_days) < 3:
        return None

    # Simple exponential smoothing
    alpha = 0.3
    smoothed = all_days[0]
    for val in all_days[1:]:
        smoothed = alpha * val + (1 - alpha) * smoothed

    # Trend detection: compare recent vs older average
    midpoint = len(all_days) // 2
    old_avg = sum(all_days[:midpoint]) / max(midpoint, 1)
    new_avg = sum(all_days[midpoint:]) / max(len(all_days) - midpoint, 1)

    if old_avg > 0:
        trend_pct = ((new_avg - old_avg) / old_avg) * 100
    else:
        trend_pct = 0

    return {
        "smoothed_rate": round(smoothed, 2),
        "trend_pct": round(trend_pct, 1),
        "data_points": len(all_days),
        "date_range": f"{dates_sorted[0]} to {dates_sorted[-1]}",
    }


def local_forecast_prediction(item: dict) -> dict:
    """
    AI-equivalent prediction using local exponential smoothing model.

    Analyzes usage_log history for the item. If enough data exists (>=3 days),
    uses exponential smoothing to forecast a usage rate that adapts to trends.
    Falls back to rule-based prediction if insufficient history.
    """
    item_id = item.get("id")
    name = item.get("name", "Item")
    quantity = item.get("quantity", 0)
    expiry = item.get("expiry_date")

    # Fetch usage history from database
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

    # Try exponential smoothing forecast
    forecast = _exponential_smoothing_forecast(usage_history)

    if forecast is None:
        # Not enough usage history - fall back to rule-based
        fallback = rule_based_prediction(item)
        fallback["method"] = "rule-based"
        fallback["note"] = "Insufficient usage history for forecasting. Log more usage to enable trend-based predictions."
        return fallback

    smoothed_rate = forecast["smoothed_rate"]
    result = {
        "item": name,
        "method": "local-forecast",
        "model": "exponential-smoothing",
        "forecast_usage_rate": smoothed_rate,
        "configured_usage_rate": item.get("daily_usage_rate", 0),
        "trend": (
            "increasing" if forecast["trend_pct"] > 10
            else "decreasing" if forecast["trend_pct"] < -10
            else "stable"
        ),
        "trend_pct": forecast["trend_pct"],
        "data_points": forecast["data_points"],
        "date_range": forecast["date_range"],
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

        result["recommendation"] = (
            f"Based on {forecast['data_points']} days of usage data, "
            f"estimated ~{days_left} days of supply remaining.{trend_note}"
        )
    else:
        result["days_until_empty"] = None
        result["urgency"] = "ok"
        result["recommendation"] = "Usage has dropped to near zero based on recent history."

    _apply_expiry_check(result, expiry)
    _apply_sustainability_tip(result, item)

    return result


def _apply_expiry_check(result: dict, expiry: Optional[str]):
    """Add expiry warnings to prediction result."""
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
    """Add sustainability suggestion for non-eco items."""
    if not item.get("is_eco_certified"):
        result["sustainability_tip"] = (
            f"Consider switching '{item.get('name', 'this item')}' to an eco-certified alternative "
            f"to reduce environmental impact."
        )


def simulate_what_if(items: list, scenario: dict) -> dict:
    """
    What-If scenario simulator: models the impact of procurement changes.

    Scenarios:
    - reduce_usage: {"item_id": 1, "reduce_pct": 20} - reduce usage by X%
    - switch_eco: {"item_id": 1} - switch item to eco-certified
    - reduce_order: {"item_id": 1, "reduce_pct": 20} - reduce order quantity by X%
    """
    action = scenario.get("action", "")
    item_id = scenario.get("item_id")
    reduce_pct = scenario.get("reduce_pct", 20)

    items_by_id = {i["id"]: dict(i) for i in items}

    # Build current baseline
    baseline = _compute_impact_metrics(items)

    # Apply scenario to a copy
    modified_items = [dict(i) for i in items]

    if action == "reduce_usage" and item_id in items_by_id:
        for i in modified_items:
            if i["id"] == item_id:
                factor = 1 - (reduce_pct / 100)
                i["daily_usage_rate"] = round(i.get("daily_usage_rate", 0) * factor, 2)
                break
        target = items_by_id[item_id]
        description = f"Reduce {target['name']} usage by {reduce_pct}%"

    elif action == "switch_eco" and item_id in items_by_id:
        for i in modified_items:
            if i["id"] == item_id:
                i["is_eco_certified"] = 1
                i["cost_per_unit"] = round(i.get("cost_per_unit", 0) * 1.15, 2)  # eco typically 15% more
                break
        target = items_by_id[item_id]
        description = f"Switch {target['name']} to eco-certified supplier"

    elif action == "reduce_order" and item_id in items_by_id:
        for i in modified_items:
            if i["id"] == item_id:
                factor = 1 - (reduce_pct / 100)
                i["quantity"] = round(i.get("quantity", 0) * factor, 1)
                break
        target = items_by_id[item_id]
        description = f"Reduce {target['name']} order by {reduce_pct}%"

    elif action == "all_eco":
        for i in modified_items:
            if not i.get("is_eco_certified"):
                i["is_eco_certified"] = 1
                i["cost_per_unit"] = round(i.get("cost_per_unit", 0) * 1.15, 2)
        description = "Switch all items to eco-certified suppliers"

    else:
        return {"error": "Unknown scenario. Use: reduce_usage, switch_eco, reduce_order, or all_eco"}

    projected = _compute_impact_metrics(modified_items)

    return {
        "scenario": description,
        "baseline": baseline,
        "projected": projected,
        "delta": {
            "waste_cost_change": round(projected["estimated_weekly_waste_cost"] - baseline["estimated_weekly_waste_cost"], 2),
            "eco_pct_change": projected["eco_pct"] - baseline["eco_pct"],
            "carbon_score_change": projected["carbon_score"] - baseline["carbon_score"],
            "weekly_cost_change": round(projected["weekly_procurement_cost"] - baseline["weekly_procurement_cost"], 2),
        },
    }


def _compute_impact_metrics(items: list) -> dict:
    """Compute waste, cost, and carbon metrics for a set of items."""
    total = len(items)
    if total == 0:
        return {"eco_pct": 0, "estimated_weekly_waste_cost": 0, "carbon_score": 0, "weekly_procurement_cost": 0}

    eco_count = sum(1 for i in items if i.get("is_eco_certified"))
    eco_pct = round(eco_count / total * 100)

    weekly_waste_cost = 0.0
    weekly_procurement_cost = 0.0
    waste_items = []

    for item in items:
        rate = item.get("daily_usage_rate", 0)
        cost = item.get("cost_per_unit", 0)
        weekly_procurement_cost += rate * 7 * cost

        exp = item.get("expiry_date")
        if exp:
            try:
                days = (datetime.strptime(exp, "%Y-%m-%d") - datetime.now()).days
                qty = item.get("quantity", 0)
                if days >= 0 and rate > 0:
                    usable = min(qty, rate * days)
                    wasted = qty - usable
                    if wasted > 0:
                        weekly_waste_cost += wasted * cost
                        waste_items.append(item.get("name", "?"))
            except ValueError:
                pass

    # Carbon score: higher is better. Eco items reduce carbon.
    carbon_score = round(eco_pct * 0.7 + max(0, 100 - len(waste_items) * 15) * 0.3)

    return {
        "eco_pct": eco_pct,
        "eco_count": eco_count,
        "total_items": total,
        "estimated_weekly_waste_cost": round(weekly_waste_cost, 2),
        "weekly_procurement_cost": round(weekly_procurement_cost, 2),
        "waste_risk_items": waste_items,
        "carbon_score": carbon_score,
    }


def answer_query(items: list, query: str) -> dict:
    """
    Rule-based natural language query handler.

    Interprets common sustainability questions and returns data-driven answers.
    This is a keyword-matching NLP approach - no LLM needed for these structured queries.
    """
    query_lower = query.lower().strip()

    # Compute current state
    metrics = _compute_impact_metrics(items)
    predictions = [rule_based_prediction(i) for i in items]
    critical = [p for p in predictions if p.get("urgency") == "critical"]
    warnings = [p for p in predictions if p.get("urgency") == "warning"]

    # Route to appropriate handler
    if any(w in query_lower for w in ["waste", "reduce waste", "throwing away", "expir"]):
        return _answer_waste(items, metrics, predictions)
    elif any(w in query_lower for w in ["save money", "cost", "spend", "expensive", "cheap"]):
        return _answer_cost(items, metrics)
    elif any(w in query_lower for w in ["reorder", "running low", "run out", "stock", "supply"]):
        return _answer_reorder(items, predictions, critical, warnings)
    elif any(w in query_lower for w in ["eco", "sustain", "green", "carbon", "environment"]):
        return _answer_sustainability(items, metrics)
    elif any(w in query_lower for w in ["summary", "overview", "status", "how are we"]):
        return _answer_summary(items, metrics, critical, warnings)
    else:
        return {
            "answer": "I can help with: waste reduction, cost savings, reorder alerts, sustainability improvements, or a general overview. Try asking something like 'How can I reduce waste?' or 'What's running low?'",
            "suggestions": [
                "How can I reduce waste this week?",
                "What items are running low?",
                "How can I improve our sustainability score?",
                "Give me a cost overview",
                "Summary of inventory status",
            ],
        }


def _answer_waste(items, metrics, predictions):
    waste_items = []
    total_waste_cost = 0
    for item in items:
        exp = item.get("expiry_date")
        rate = item.get("daily_usage_rate", 0)
        qty = item.get("quantity", 0)
        cost = item.get("cost_per_unit", 0)
        if exp and rate > 0:
            try:
                days = (datetime.strptime(exp, "%Y-%m-%d") - datetime.now()).days
                if days >= 0:
                    usable = min(qty, rate * days)
                    wasted = qty - usable
                    if wasted > 0:
                        waste_items.append({
                            "name": item["name"],
                            "wasted_qty": round(wasted, 1),
                            "unit": item.get("unit", ""),
                            "wasted_cost": round(wasted * cost, 2),
                            "expires_in_days": days,
                            "suggestion": f"Reduce next order by {round(wasted)} {item.get('unit', 'units')} or use/donate before expiry.",
                        })
                        total_waste_cost += wasted * cost
            except ValueError:
                pass

    if not waste_items:
        return {"answer": "Great news! No items are currently at risk of waste. Your ordering is well-calibrated to usage.", "waste_items": [], "actions": []}

    actions = [f"Reduce {w['name']} order by {w['wasted_qty']} {w['unit']} (saves ${w['wasted_cost']})" for w in waste_items[:3]]

    return {
        "answer": f"You have {len(waste_items)} item(s) at risk of waste, costing ~${round(total_waste_cost, 2)}. Here's how to reduce it:",
        "waste_items": waste_items,
        "total_waste_cost": round(total_waste_cost, 2),
        "actions": actions,
    }


def _answer_cost(items, metrics):
    # Find most expensive items by weekly cost
    item_costs = []
    for item in items:
        rate = item.get("daily_usage_rate", 0)
        cost = item.get("cost_per_unit", 0)
        weekly = rate * 7 * cost
        if weekly > 0:
            item_costs.append({"name": item["name"], "weekly_cost": round(weekly, 2), "is_eco": bool(item.get("is_eco_certified"))})

    item_costs.sort(key=lambda x: x["weekly_cost"], reverse=True)

    return {
        "answer": f"Weekly procurement cost: ${metrics['weekly_procurement_cost']}. Waste adds ~${metrics['estimated_weekly_waste_cost']} in losses.",
        "top_costs": item_costs[:5],
        "actions": [
            f"Biggest expense: {item_costs[0]['name']} at ${item_costs[0]['weekly_cost']}/week" if item_costs else "No recurring costs found",
            f"Waste cost: ${metrics['estimated_weekly_waste_cost']}/week - reducible by right-sizing orders",
        ],
    }


def _answer_reorder(items, predictions, critical, warnings):
    urgent = []
    for p in critical + warnings:
        item_name = p["item"]
        days = p.get("days_until_empty")
        urgent.append({"name": item_name, "days_left": days, "urgency": p["urgency"]})

    if not urgent:
        return {"answer": "All items have sufficient stock. No reorders needed right now.", "items": [], "actions": []}

    return {
        "answer": f"{len(critical)} critical and {len(warnings)} items need attention:",
        "items": urgent,
        "actions": [f"Reorder {u['name']} ({u['days_left']} days left)" for u in urgent[:5]],
    }


def _answer_sustainability(items, metrics):
    non_eco = [i for i in items if not i.get("is_eco_certified")]
    non_eco_names = [i["name"] for i in non_eco[:5]]

    return {
        "answer": f"Sustainability score: {metrics['carbon_score']}/100. {metrics['eco_pct']}% of items are eco-certified ({metrics['eco_count']}/{metrics['total_items']}).",
        "non_eco_items": non_eco_names,
        "actions": [
            f"Switch {n} to an eco-certified alternative" for n in non_eco_names[:3]
        ] + (["Switching all items to eco could raise your score significantly"] if non_eco else []),
    }


def _answer_summary(items, metrics, critical, warnings):
    return {
        "answer": f"Inventory: {len(items)} items. {len(critical)} critical, {len([w for w in warnings])} warnings. Eco score: {metrics['eco_pct']}%. Weekly cost: ${metrics['weekly_procurement_cost']}. Waste risk: ${metrics['estimated_weekly_waste_cost']}.",
        "metrics": metrics,
        "actions": [
            f"Address {len(critical)} critical items first" if critical else "No critical items",
            f"Reduce waste to save ${metrics['estimated_weekly_waste_cost']}/week" if metrics['estimated_weekly_waste_cost'] > 0 else "No waste detected",
        ],
    }


def calculate_sustainability_score(items: list) -> dict:
    """Calculate a sustainability impact score for the inventory."""
    total = len(items)
    if total == 0:
        return {"score": 0, "breakdown": {}}

    eco_count = sum(1 for i in items if i.get("is_eco_certified"))
    eco_pct = round(eco_count / total * 100)

    waste_risk_items = 0
    estimated_waste_cost = 0.0
    for item in items:
        exp = item.get("expiry_date")
        if exp:
            try:
                days = (datetime.strptime(exp, "%Y-%m-%d") - datetime.now()).days
                if days <= 3 and item.get("quantity", 0) > 0:
                    waste_risk_items += 1
                    estimated_waste_cost += item.get("quantity", 0) * item.get("cost_per_unit", 0)
            except ValueError:
                pass

    waste_score = max(0, 100 - (waste_risk_items * 25))
    overall = round((eco_pct + waste_score) / 2)

    return {
        "overall_score": overall,
        "eco_certified_pct": eco_pct,
        "waste_management_score": waste_score,
        "eco_certified_count": eco_count,
        "total_items": total,
        "waste_risk_items": waste_risk_items,
        "estimated_waste_cost": round(estimated_waste_cost, 2),
        "grade": "A" if overall >= 80 else "B" if overall >= 60 else "C" if overall >= 40 else "D",
    }
