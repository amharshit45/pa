"""Sustainability Engine - Scores, impact metrics, and what-if simulation."""

from datetime import datetime


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


def simulate_what_if(items: list, scenario: dict) -> dict:
    """Model the impact of procurement changes before committing."""
    action = scenario.get("action", "")
    item_id = scenario.get("item_id")
    reduce_pct = scenario.get("reduce_pct", 20)

    items_by_id = {i["id"]: dict(i) for i in items}
    baseline = compute_impact_metrics(items)
    modified_items = [dict(i) for i in items]

    if action == "reduce_usage" and item_id in items_by_id:
        for i in modified_items:
            if i["id"] == item_id:
                i["daily_usage_rate"] = round(i.get("daily_usage_rate", 0) * (1 - reduce_pct / 100), 2)
                break
        description = f"Reduce {items_by_id[item_id]['name']} usage by {reduce_pct}%"

    elif action == "switch_eco" and item_id in items_by_id:
        for i in modified_items:
            if i["id"] == item_id:
                i["is_eco_certified"] = 1
                i["cost_per_unit"] = round(i.get("cost_per_unit", 0) * 1.15, 2)
                break
        description = f"Switch {items_by_id[item_id]['name']} to eco-certified supplier"

    elif action == "reduce_order" and item_id in items_by_id:
        for i in modified_items:
            if i["id"] == item_id:
                i["quantity"] = round(i.get("quantity", 0) * (1 - reduce_pct / 100), 1)
                break
        description = f"Reduce {items_by_id[item_id]['name']} order by {reduce_pct}%"

    elif action == "all_eco":
        for i in modified_items:
            if not i.get("is_eco_certified"):
                i["is_eco_certified"] = 1
                i["cost_per_unit"] = round(i.get("cost_per_unit", 0) * 1.15, 2)
        description = "Switch all items to eco-certified suppliers"

    else:
        return {"error": "Unknown scenario. Use: reduce_usage, switch_eco, reduce_order, or all_eco"}

    projected = compute_impact_metrics(modified_items)

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


def compute_impact_metrics(items: list) -> dict:
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
