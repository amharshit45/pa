"""
API Gateway - Thin routing layer that delegates to service modules.

Architecture:
  [React Frontend] -> [FastAPI Gateway] -> [Services] -> [SQLite DB]

Services:
  - inventory_service: CRUD, search, usage logging
  - prediction_engine: Exponential smoothing + rule-based fallback
  - ai_service: Natural language query processing (rule-based NLP)
  - sustainability_engine: Scores, impact metrics, what-if simulation
"""

import os

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional
from database import init_db, seed_from_json
from services.inventory_service import (
    list_items, get_item, create_item, update_item, delete_item,
    log_usage, get_all_items, get_categories,
)
from services.prediction_engine import local_forecast_prediction, predict_all
from services.sustainability_engine import calculate_sustainability_score, simulate_what_if
from services.ai_service import answer_query

app = FastAPI(title="Green-Tech Inventory Co-Pilot")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Request Models ---

class ItemCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    category: str = Field(default="Supplies")
    quantity: float = Field(..., ge=0)
    unit: str = Field(default="pieces", min_length=1)
    expiry_date: Optional[str] = None
    daily_usage_rate: float = Field(default=0, ge=0)
    cost_per_unit: float = Field(default=0, ge=0)
    supplier: str = Field(default="")
    is_eco_certified: bool = False
    storage_condition: str = Field(default="room_temp")
    notes: str = Field(default="")


class ItemUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    category: Optional[str] = None
    quantity: Optional[float] = Field(None, ge=0)
    unit: Optional[str] = None
    expiry_date: Optional[str] = None
    daily_usage_rate: Optional[float] = Field(None, ge=0)
    cost_per_unit: Optional[float] = Field(None, ge=0)
    supplier: Optional[str] = None
    is_eco_certified: Optional[bool] = None
    storage_condition: Optional[str] = None
    notes: Optional[str] = None


class UsageLog(BaseModel):
    quantity_used: float = Field(..., gt=0)


class WhatIfScenario(BaseModel):
    action: str = Field(..., description="reduce_usage, switch_eco, reduce_order, or all_eco")
    item_id: Optional[int] = None
    reduce_pct: float = Field(default=20, ge=1, le=100)


class ChatQuery(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)


# --- Startup ---

@app.on_event("startup")
def startup():
    init_db()
    seed_from_json()


# --- Inventory Routes -> inventory_service ---

@app.get("/api/items")
def api_list_items(
    search: str = Query("", description="Search by name or supplier"),
    category: str = Query("", description="Filter by category"),
    urgency: str = Query("", description="Filter: critical, warning, ok"),
):
    return list_items(search, category, urgency)


@app.post("/api/items", status_code=201)
def api_create_item(item: ItemCreate):
    return create_item(item.model_dump())


@app.get("/api/items/{item_id}")
def api_get_item(item_id: int):
    result = get_item(item_id)
    if not result:
        raise HTTPException(404, "Item not found")
    return result


@app.put("/api/items/{item_id}")
def api_update_item(item_id: int, updates: ItemUpdate):
    fields = {k: v for k, v in updates.model_dump().items() if v is not None}
    if not fields:
        raise HTTPException(400, "No fields to update")
    result = update_item(item_id, fields)
    if not result:
        raise HTTPException(404, "Item not found")
    return result


@app.delete("/api/items/{item_id}")
def api_delete_item(item_id: int):
    if not delete_item(item_id):
        raise HTTPException(404, "Item not found")
    return {"message": "Item deleted"}


@app.post("/api/items/{item_id}/usage")
def api_log_usage(item_id: int, usage: UsageLog):
    result = log_usage(item_id, usage.quantity_used)
    if "error" in result:
        if result["error"] == "not_found":
            raise HTTPException(404, "Item not found")
        raise HTTPException(400, f"Insufficient stock. Current: {result['current']} {result['unit']}")
    return result


@app.get("/api/categories")
def api_categories():
    return get_categories()


# --- Prediction Routes -> prediction_engine ---

@app.get("/api/items/{item_id}/predict")
def api_predict_item(item_id: int):
    item = get_item(item_id)
    if not item:
        raise HTTPException(404, "Item not found")
    return local_forecast_prediction(item)


@app.get("/api/predictions")
def api_predict_all():
    return predict_all(get_all_items())


# --- Sustainability Routes -> sustainability_engine ---

@app.get("/api/sustainability")
def api_sustainability():
    return calculate_sustainability_score(get_all_items())


@app.post("/api/what-if")
def api_what_if(scenario: WhatIfScenario):
    items = get_all_items()
    if not items:
        raise HTTPException(400, "No items in inventory")
    if scenario.item_id:
        if scenario.item_id not in {i["id"] for i in items}:
            raise HTTPException(404, "Item not found")
    return simulate_what_if(items, scenario.model_dump())


# --- AI Routes -> ai_service ---

@app.post("/api/chat")
def api_chat(q: ChatQuery):
    return answer_query(get_all_items(), q.query)


# --- Static Files (serves React build) ---

if os.path.exists("frontend/dist"):
    app.mount("/assets", StaticFiles(directory="frontend/dist/assets"), name="assets")

    @app.get("/{full_path:path}")
    def serve_react(full_path: str):
        return FileResponse("frontend/dist/index.html")
