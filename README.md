# Green-Tech Inventory Co-Pilot

**Candidate Name:** Harshit Goyal

**Scenario Chosen:** Green-Tech Inventory Assistant

**Estimated Time Spent:** ~5 hours

An intelligent sustainability co-pilot for physical inventory that goes beyond tracking. It helps small businesses and community organizations **make better procurement decisions** by simulating the waste, cost, and carbon impact of changes before they happen.

## Quick Start

### Prerequisites
- Python 3.9+
- Node.js 18+ (for frontend development only; production build is pre-compiled)

### Run Commands

```bash
# Install Python dependencies
pip install -r requirements.txt

# Start the server
uvicorn app:app --reload
```

Open http://localhost:8000 in your browser.

### Demo

[Link](https://drive.google.com/drive/folders/1AIPr1-Qg7Y-4YVK7XaVrG7ySvrl2478G?usp=sharing)

### Frontend Development

```bash
cd frontend
npm install
npm run dev        # Dev server at http://localhost:5173
npm run build      # Production build to frontend/dist/
```

The FastAPI server serves the production React build from `frontend/dist/`. During development, the React dev server proxies API calls to the backend via CORS.

### Test Commands

```bash
python -m pytest tests/ -v
```

## Architecture

```
[Frontend (React + Vite)]
        |
[API Gateway (FastAPI)]
        |
 +-----------+-----------------+-----------------+
 |           |                 |                 |
[Inventory] [AI Service]  [Prediction      [Sustainability
 Service]    (Rule-NLP)    Engine]            Engine]
 |           |              (Holt's Linear    (Heuristics +
 |           |               + Shelf Life)     Alternatives DB)
 |           |                 |                 |
 +-----------+-----------+-----+-----------------+
                         |
                    [SQLite DB]
```

### Project Structure

```
pa/
+-- app.py                    # API gateway - thin routing layer
+-- database.py               # SQLite connection, schema, seeding
+-- services/
|   +-- inventory_service.py  # CRUD, search, usage logging
|   +-- prediction_engine.py  # Holt's linear trend + seasonality + shelf life prediction + rule-based fallback
|   +-- ai_service.py         # Rule-based NLP chat co-pilot
|   +-- sustainability_engine.py  # Scores, impact metrics, what-if, sustainable alternatives
+-- frontend/
|   +-- src/
|   |   +-- App.jsx           # Main app with tab navigation
|   |   +-- api.js            # API client helper
|   |   +-- components/
|   |       +-- CoPilot.jsx       # Chat interface with suggestion chips + alternative recommendations
|   |       +-- Inventory.jsx     # Searchable/filterable item table
|   |       +-- ItemModal.jsx     # Add/edit item form modal (incl. storage condition)
|   |       +-- Predictions.jsx   # ML forecast cards + shelf life predictions
|   |       +-- Sustainability.jsx # Score ring + grade dashboard + sustainable alternatives
|   |       +-- WhatIf.jsx        # Scenario simulator with comparison grid
|   +-- dist/                 # Production build (served by FastAPI)
+-- tests/
|   +-- test_app.py           # 33 tests (happy paths + edge cases + forecasting + shelf life + alternatives + caching)
+-- data/
|   +-- sample_data.json              # 10 synthetic inventory items (with storage conditions)
|   +-- sample_usage_logs.json        # Pre-generated 60-day usage history (static, deterministic)
|   +-- sustainable_alternatives.json # Eco-friendly alternative products database
+-- requirements.txt
```

## Features

### Sustainability Co-Pilot (Chat Interface)
Ask natural language questions and get data-driven answers:
- **"How can I reduce waste this week?"** - Identifies items at risk of expiry with specific quantity and cost savings
- **"What items are running low?"** - Shows critical/warning items with days remaining
- **"How can I improve our sustainability score?"** - Lists non-eco items with **specific alternative product recommendations** (name, supplier, cost, carbon reduction %)
- **"What are the sustainable alternatives?"** - Shows eco-friendly replacements for non-certified items
- **"Give me a cost overview"** - Shows weekly procurement costs and waste losses
- Rule-based NLP (keyword matching) - no cloud LLM needed for structured inventory queries

### Shelf Life Prediction
Predicts **effective shelf life** beyond just the expiry date label:
- **Storage condition tracking**: Each item records its storage type (frozen, refrigerated, room temp, warm)
- **Storage multipliers**: Perishables at room temp degrade faster (0.6x shelf life) vs refrigerated (1.0x) vs frozen (3.0x)
- **Handling frequency factor**: High-turnover items (frequently accessed stock) experience faster quality degradation
- **Nominal vs effective comparison**: Shows how many days are lost due to storage/handling conditions
- **Actionable recommendations**: Suggests refrigerating room-temp perishables when effective shelf life is significantly reduced
- Works for all categories with sensible defaults (Perishable: 7d, Supplies: 365d, Equipment: 730d)

### Sustainable Procurement Alternatives
Specific eco-friendly replacement suggestions for non-certified items:
- **Alternatives database** (`data/sustainable_alternatives.json`): Named products with supplier, cost, eco-certifications, and carbon footprint reduction estimates
- **Fuzzy name matching**: 3-tier lookup (exact → case-insensitive → `difflib.SequenceMatcher` with 0.6 threshold) so items like "whole milk" or "Lab Gloves" match their alternatives without exact casing or naming
- **Sustainability dashboard integration**: Shows available alternatives directly below the score ring with cost comparisons
- **Chat co-pilot integration**: Sustainability queries return specific product names, suppliers, and carbon reduction percentages
- **What-If accuracy**: "Switch to eco" scenarios use **real alternative costs** from the database instead of a generic 15% markup
- Covers all non-eco sample items (Almond Croissants, Whole Milk, Lab Gloves) with 1-2 alternatives each

### What-If Scenario Simulator
Model procurement changes before committing:
- **Reduce usage**: "What if I reduce coffee orders by 20%?" -> Shows waste/cost/carbon impact
- **Switch supplier**: "What if I switch cups to eco-certified?" -> Uses real alternative product costs and shows sustainability score change
- **Go all-eco**: "What if everything was eco-certified?" -> Full portfolio impact analysis with per-item alternative costs
- Comparison grid: Baseline vs. Projected with delta indicators

### Core Flow (CRUD + Search/Filter)
- **Create**: Add inventory items with name, category, quantity, expiry date, usage rate, supplier, storage condition, and eco-certification
- **View**: Browse all items in a searchable, filterable table
- **Update**: Edit any item's fields inline
- **Delete**: Remove items with confirmation
- **Search**: Debounced real-time text search across item names and suppliers
- **Filter**: Filter by category (Perishable, Supplies, Equipment)

### Local AI Forecasting: Predictive Reorder Insights
- Uses **Holt's double exponential smoothing** (level + trend) on 60 days of usage history for accurate trend-aware forecasting
- **Weekly seasonality detection**: Identifies day-of-week usage patterns (e.g., cafe items spiking on weekends) with seasonal indices and peak/trough days
- **Confidence scoring**: Data-quality heuristic combining data point count and model fit (MAE)
- Detects increasing/decreasing/stable usage trends with per-day trend rate
- **Static usage history**: Pre-generated 60-day usage logs stored in `data/sample_usage_logs.json` (deterministic, editable, anchored to a fixed date)
- **Forecast caching**: In-memory cache per item keyed by usage log count — skips redundant Holt's computation when usage history hasn't changed, automatically invalidated on new usage logs or item deletion
- Zero cost, zero latency, works fully offline - no API keys needed
- **Fallback**: Rule-based prediction (quantity / daily_usage_rate) when insufficient usage history (<3 days of logs)

### Sustainability Impact Score
- Dashboard with score ring and letter grade (A-D)
- Tracks eco-certified product percentage
- Identifies waste-risk items (near expiry with remaining stock)
- Carbon score combining eco-certification (70%) and waste metrics (30%)
- **Sustainable alternatives section**: Lists specific eco-friendly replacements with cost, supplier, certifications, and carbon reduction %
- **Score impact preview**: Each alternative shows the projected sustainability score improvement if that item were switched (e.g., "Score: 65 → 72 (+7)")

## Tech Stack

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| Frontend | React + Vite | Component-based UI, fast HMR, production-optimized builds |
| API Gateway | Python + FastAPI | Lightweight, built-in Pydantic validation, auto OpenAPI docs |
| Database | SQLite (WAL mode) | Zero-config, file-based, perfect for small orgs |
| Forecasting | Holt's linear trend + seasonality + shelf life | Zero cost, offline, trend-aware, right-sized for time-series |
| NLP | Rule-based keyword matching | Handles structured queries without cloud API costs |
| Testing | pytest + httpx | FastAPI's recommended test stack |

## Architecture Decisions

- **Service-layer architecture**: Thin API gateway delegates to 4 focused service modules. Each service owns its logic and can be tested independently
- **React frontend**: Component-based UI with tab navigation, modals, and debounced search. Served as static files from FastAPI in production; CORS-enabled dev server for development
- **Decision intelligence, not just tracking**: The What-If simulator and Co-Pilot chat turn passive inventory data into actionable procurement decisions
- **Local forecasting over cloud LLM**: Holt's linear trend model is more appropriate, cheaper, and faster than calling an LLM for numerical time-series prediction
- **Rule-based NLP**: For structured inventory queries ("what's running low?", "reduce waste"), keyword matching delivers reliable answers without API costs or latency
- **Graceful degradation**: Local forecast when enough usage data exists, rule-based when not
- **Static usage data**: Pre-generated usage logs stored as JSON rather than generated at runtime. This makes the sample data transparent, editable, and fully deterministic regardless of when the app is first run
- **Shelf life prediction model**: Combines storage condition multipliers with handling frequency factors to predict effective shelf life. Perishables stored at room temperature get a 0.6x multiplier; frequently accessed items degrade faster due to handling exposure
- **Alternatives database over generic markup**: Sustainable procurement alternatives use a curated JSON database with real product names, suppliers, and costs rather than applying a blanket 15% eco-premium. Fuzzy matching via `difflib.SequenceMatcher` (0.6 threshold) handles case variations and partial name matches without external dependencies
- **Forecast caching**: Holt's smoothing results are cached in-memory per item, keyed by usage log count as a staleness check. This eliminates redundant computation when predictions are requested multiple times without new usage data. Cache is explicitly invalidated on usage logging and item deletion

## AI Disclosure

- **Did you use an AI assistant?** Yes (Claude Code)
- **How did you verify suggestions?** Ran all 33 tests, manually tested the web UI including chat and what-if scenarios, verified edge cases (empty names, negative quantities, missing items, stock overuse, unknown queries, shelf life predictions, alternative suggestions, forecast caching, score impact preview)
- **Example of a rejected/changed suggestion:** Initial design used Claude API (Haiku) for predictions. Rejected this in favor of local exponential smoothing because the core task is numerical time-series forecasting, not natural language processing - a local model is free, faster, and more appropriate for small organizations.

## Tradeoffs & Prioritization

### What was cut
- Visual asset scanning (photo-based inventory) - would require computer vision integration
- Usage history charts/trends - the usage_log table exists but no visualization yet
- User authentication - not needed for MVP
- Notifications/alerts - would need background jobs

### What I'd build next
1. **Usage trend charts**: Chart.js visualization of consumption patterns from usage_log
2. **Seasonality-adjusted forecasts**: Use detected weekly indices to adjust the Holt forecast per-day (currently informational only)
3. **Batch import**: CSV upload for bulk inventory entry
4. **Multi-user support**: Auth + role-based access for team use
5. **Expanded supplier database**: More alternatives with real-time pricing and availability

### Known Limitations
- No authentication (single-user assumed)
- Forecast requires 3+ days of usage logs to activate; new items use rule-based fallback
- Chat NLP uses keyword matching - won't handle very creative phrasing
- Carbon score is a simplified heuristic combining eco-certification and waste metrics
- Shelf life prediction uses category-based heuristics rather than product-specific degradation curves
- Alternatives database covers sample items only; new items without matching entries get generic suggestions
- SQLite limits concurrent write access (fine for small teams)
