"""AI Service - Natural language query processing (rule-based NLP)."""

from datetime import datetime
from services.prediction_engine import rule_based_prediction
from services.sustainability_engine import compute_impact_metrics, get_alternatives_for_item


def answer_query(items: list, query: str) -> dict:
    """
    Rule-based NLP query handler.

    Interprets common sustainability questions and returns data-driven answers.
    Keyword-matching approach - no LLM needed for structured inventory queries.
    """
    query_lower = query.lower().strip()

    metrics = compute_impact_metrics(items)
    predictions = [rule_based_prediction(i) for i in items]
    critical = [p for p in predictions if p.get("urgency") == "critical"]
    warnings = [p for p in predictions if p.get("urgency") == "warning"]

    if any(w in query_lower for w in ["waste", "reduce waste", "throwing away", "expir"]):
        return _answer_waste(items, metrics)
    elif any(w in query_lower for w in ["save money", "cost", "spend", "expensive", "cheap"]):
        return _answer_cost(items, metrics)
    elif any(w in query_lower for w in ["reorder", "running low", "run out", "stock", "supply"]):
        return _answer_reorder(critical, warnings)
    elif any(w in query_lower for w in ["eco", "sustain", "green", "carbon", "environment", "alternative", "procurement"]):
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


def _answer_waste(items, metrics):
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


def _answer_reorder(critical, warnings):
    urgent = []
    for p in critical + warnings:
        urgent.append({"name": p["item"], "days_left": p.get("days_until_empty"), "urgency": p["urgency"]})

    if not urgent:
        return {"answer": "All items have sufficient stock. No reorders needed right now.", "items": [], "actions": []}

    return {
        "answer": f"{len(critical)} critical and {len(warnings)} items need attention:",
        "items": urgent,
        "actions": [f"Reorder {u['name']} ({u['days_left']} days left)" for u in urgent[:5]],
    }


def _answer_sustainability(items, metrics):
    non_eco = [i for i in items if not i.get("is_eco_certified")][:5]
    non_eco_names = [i["name"] for i in non_eco]

    actions = []
    alternative_details = []
    for item in non_eco[:3]:
        alts = get_alternatives_for_item(item)
        if alts:
            best = alts[0]
            actions.append(
                f"Switch {item['name']} to {best['alternative_name']} "
                f"(by {best['supplier']}, ~${best['estimated_cost_per_unit']}/unit, "
                f"~{best['carbon_footprint_reduction_pct']}% carbon reduction)"
            )
            alternative_details.append({
                "current_item": item["name"],
                "alternatives": alts,
            })
        else:
            actions.append(f"Switch {item['name']} to an eco-certified alternative")

    if non_eco:
        actions.append("Switching all items to eco could raise your score significantly")

    return {
        "answer": f"Sustainability score: {metrics['carbon_score']}/100. {metrics['eco_pct']}% of items are eco-certified ({metrics['eco_count']}/{metrics['total_items']}).",
        "non_eco_items": non_eco_names,
        "alternative_details": alternative_details,
        "actions": actions,
    }


def _answer_summary(items, metrics, critical, warnings):
    return {
        "answer": f"Inventory: {len(items)} items. {len(critical)} critical, {len(warnings)} warnings. Eco score: {metrics['eco_pct']}%. Weekly cost: ${metrics['weekly_procurement_cost']}. Waste risk: ${metrics['estimated_weekly_waste_cost']}.",
        "metrics": metrics,
        "actions": [
            f"Address {len(critical)} critical items first" if critical else "No critical items",
            f"Reduce waste to save ${metrics['estimated_weekly_waste_cost']}/week" if metrics['estimated_weekly_waste_cost'] > 0 else "No waste detected",
        ],
    }
