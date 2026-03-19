# Design Documentation: Green-Tech Inventory Co-Pilot

## Overview

The Green-Tech Inventory Co-Pilot is a lightweight, AI-powered inventory management tool designed for small businesses, non-profits, and community organizations. It helps track physical assets, predict stock depletion using local ML forecasting, and promote sustainable procurement decisions through a What-If simulator and chat co-pilot.

## Tech Stack


| Component       | Technology                                        | Justification                                                                |
| --------------- | ------------------------------------------------- | ---------------------------------------------------------------------------- |
| **Frontend**    | React + Vite (JSX)                                | Component-based UI, fast HMR in dev, optimized production builds             |
| **API Gateway** | Python 3.9 + FastAPI                              | Lightweight, async-capable, auto-generated OpenAPI docs, Pydantic validation |
| **Database**    | SQLite (WAL mode)                                 | Zero configuration, single-file storage, ideal for small organizations       |
| **Forecasting** | Holt's double exponential smoothing + seasonality | Zero cost, no API keys, works offline, trend-aware, runs on usage_log data   |
| **Fallback**    | Rule-based math engine                            | Deterministic fallback when insufficient usage history (<3 days)             |
| **NLP**         | Rule-based keyword matching                       | Handles structured inventory queries without cloud API costs                 |
| **Testing**     | pytest + FastAPI TestClient                       | First-class FastAPI integration, simple assertion model                      |


## Architecture

```
 [Frontend (React + Vite)]
          |
          | REST API (JSON)
          |
 [API Gateway / Backend (FastAPI)]
          |
   +------+----------+-----------------+-----------------+
   |                  |                 |                 |
 [Inventory       [AI Service]    [Prediction       [Sustainability
  Service]         (Rule-NLP)      Engine]            Engine]
   |                  |            (Holt's Linear)     (Heuristics)
   |                  |                 |                 |
   +------+-----------+--------+--------+-----------------+
                               |
                          [SQLite DB]
                        (items + usage_log)
```

### Service Layer Design

The backend follows a **thin gateway + service modules** pattern:

- `**app.py`** (API Gateway): Route definitions, request/response models (Pydantic), CORS middleware, static file serving. Contains zero business logic — every handler delegates to a service function.
- `**services/inventory_service.py**`: CRUD operations, search/filter, usage logging. Owns all direct item table interactions.
- `**services/prediction_engine.py**`: Holt's double exponential smoothing (level + trend) with weekly seasonality detection, confidence scoring, and rule-based fallback. Reads from `usage_log` to build time-series data.
- `**services/ai_service.py**`: Rule-based NLP for the chat co-pilot. Routes queries by keyword to domain-specific answer functions.
- `**services/sustainability_engine.py**`: Sustainability scoring, impact metrics, What-If scenario simulation.

### Frontend Architecture

React SPA with tab-based navigation and shared state:

- `**App.jsx**`: Root component managing shared `items` state, sustainability badge, and tab switching
- `**api.js**`: Centralized API client (`fetch` wrapper with base URL and error handling)
- `**CoPilot.jsx**`: Chat interface with message history, suggestion chips, and structured bot responses
- `**Inventory.jsx**`: Item table with debounced search (300ms), category filter, inline actions (edit/predict/delete)
- `**ItemModal.jsx**`: Form modal for create/edit with client-side validation
- `**Predictions.jsx**`: Fetches ML predictions on mount, sorts by urgency, renders forecast cards with model/method badges, trend arrows, confidence indicators, and seasonality descriptions
- `**Sustainability.jsx**`: Score ring visualization, letter grade, stats row
- `**WhatIf.jsx**`: Scenario form with dynamic fields, comparison grid with green/red delta indicators

In production, FastAPI serves the built React app from `frontend/dist/`. During development, the Vite dev server runs on port 5173 with CORS allowing cross-origin API calls to port 8000.

## Data Model

### Items Table


| Column           | Type          | Description                        |
| ---------------- | ------------- | ---------------------------------- |
| id               | INTEGER PK    | Auto-incrementing identifier       |
| name             | TEXT NOT NULL | Item name (1-200 chars)            |
| category         | TEXT          | Perishable, Supplies, or Equipment |
| quantity         | REAL          | Current stock level (>=0)          |
| unit             | TEXT          | Unit of measurement                |
| expiry_date      | TEXT          | ISO date string (nullable)         |
| daily_usage_rate | REAL          | Average daily consumption          |
| cost_per_unit    | REAL          | Cost for waste calculations        |
| supplier         | TEXT          | Supplier name for search           |
| is_eco_certified | INTEGER       | Boolean (0/1) for sustainability   |
| notes            | TEXT          | Free-form notes                    |
| created_at       | TIMESTAMP     | Auto-set on creation               |
| updated_at       | TIMESTAMP     | Auto-set on modification           |


### Usage Log Table


| Column        | Type       | Description                  |
| ------------- | ---------- | ---------------------------- |
| id            | INTEGER PK | Auto-incrementing identifier |
| item_id       | INTEGER FK | References items(id)         |
| quantity_used | REAL       | Amount consumed              |
| logged_at     | TIMESTAMP  | When usage was recorded      |


### Synthetic Data Seeding

On first startup, `seed_from_json()` loads 10 items from `data/sample_data.json`, then `_seed_usage_logs()` generates **60 days (2 months) of synthetic usage history** per item:

- Usage varies ±20% around the item's `daily_usage_rate` for realism
- **Day-of-week seasonal multipliers** applied per category:
  - *Perishable* items use `WEEKEND_SEASONAL` (peak on Saturday at 1.25x, trough on Tuesday at 0.85x)
  - *Supplies/Equipment* items use `WEEKDAY_SEASONAL` (peak Mon-Tue at 1.10x, trough Sat-Sun at 0.85x)
- A gentle upward trend factor (+0.2% per day, up to +12% over 60 days) simulates gradual demand increase
- Seeded with `random.seed(42)` for reproducible demo data
- 60 days of data ensures "high" confidence from the seasonality detector (≥28 days) and robust Holt's model fitting with 8+ full weekly cycles

## AI/Forecasting Integration Design

### Design Decision: Local Forecasting over Cloud LLM

An earlier version used the Anthropic Claude API (Haiku) for predictions. However, since the core task is numerical time-series forecasting (predicting when stock runs out based on usage patterns), a local statistical model is a much better fit:


| Factor                       | Cloud LLM (Claude) | Local Forecasting    |
| ---------------------------- | ------------------ | -------------------- |
| **Cost**                     | ~$0.001/prediction | Free                 |
| **Latency**                  | 500ms-2s (network) | <1ms                 |
| **Offline**                  | No                 | Yes                  |
| **Accuracy for time-series** | Approximate        | Precise (math-based) |
| **Dependencies**             | API key, internet  | None                 |
| **Appropriate for task**     | Overkill           | Right-sized          |


For small organizations tracking inventory, paying per-API-call for what is essentially `quantity / usage_rate` with trend detection is unnecessary expense.

### Evolution: From Simple Smoothing to Holt's Method

The prediction engine was upgraded from simple exponential smoothing (SES) to **Holt's double exponential smoothing** with weekly seasonality detection. Key reasons:

1. **SES has no explicit trend model** — it tracks only a smoothed level. When usage is steadily rising, SES lags behind because it blends new values with historical levels. Holt's method adds a separate trend component that explicitly tracks the rate of change.
2. **Weekly patterns are invisible to SES** — a cafe that uses 25% more milk on Saturdays looks the same as one with random variance. Dedicated seasonality detection identifies these patterns as actionable intelligence.
3. **Confidence was implicit** — SES provided no signal about how trustworthy a forecast was. The new confidence scorer uses both data quantity and model fit quality (MAE).

### Primary: Holt's Linear Trend Forecast (`local_forecast_prediction`)

Uses the `usage_log` table to build a history of actual consumption, then applies Holt's double exponential smoothing to forecast daily usage rates with explicit trend tracking.

Algorithm — Holt's double exponential smoothing:

```
L(t) = alpha * X(t) + (1 - alpha) * (L(t-1) + T(t-1))    # Level update
T(t) = beta  * (L(t) - L(t-1)) + (1 - beta) * T(t-1)      # Trend update
Forecast: F(t+1) = L(t) + T(t)
```

Parameters: `alpha = 0.3` (level smoothing), `beta = 0.1` (conservative trend damping to avoid overreacting to noise).

Full pipeline:

```
1. Fetch usage_log entries for the item (SELECT ... WHERE item_id = ?)
2. Group by date, fill zero-usage gaps between first and last log date
3. Apply Holt's smoothing to compute level (L) and trend (T) components
4. Track in-sample fitted values and compute MAE for confidence scoring
5. Detect weekly seasonality via day-of-week seasonal indices
6. Compute confidence heuristic (data points + MAE quality)
7. Trend classification: trend_pct = T/L * 100 (>10% = increasing, <-10% = decreasing)
8. Forecast days_until_empty = current_quantity / (L + T)
9. Generate recommendation with trend and seasonality context
```

### Weekly Seasonality Detection (`detect_weekly_seasonality`)

Groups usage values by day-of-week (Mon=0 through Sun=6) and computes seasonal indices:

```
seasonal_index[weekday] = weekday_mean / overall_mean
```

An index of 1.25 on Saturday means usage is 25% above average on Saturdays. Seasonality is flagged as "detected" when the standard deviation of the 7 indices exceeds 0.10 (i.e., there's meaningful variance across days).

Confidence tiers for seasonality: <14 days → "low", 14-27 → "medium", ≥28 → "high". With 60 days of seed data, all items start at "high" confidence.

Output includes: `detected`, `indices` (per-day map), `peak_day`, `trough_day`, `peak_multiplier`, `confidence`, `description`.

### Confidence Scoring (`compute_confidence`)

Heuristic combining data quantity and model fit:


| Factor           | Low            | Medium | High         |
| ---------------- | -------------- | ------ | ------------ |
| Data points      | <7             | 7-20   | 21+          |
| MAE as % of mean | >30% (penalty) | 15-30% | <15% (boost) |


### Forecast Output Fields

Output includes: `method: "local-forecast"`, `model: "holt-linear"`, `forecast_usage_rate`, `trend` (increasing/decreasing/stable), `trend_pct`, `trend_per_day`, `data_points`, `date_range`, `seasonality` (object), `confidence` (low/medium/high).

### Fallback: Rule-Based Engine (`rule_based_prediction`)

Activates when insufficient usage history exists (<3 daily data points):

```
if daily_usage_rate > 0:
    days_until_empty = quantity / daily_usage_rate
    if days_until_empty <= 2: urgency = "critical"
    elif days_until_empty <= 7: urgency = "warning"
    else: urgency = "ok"
else:
    days_until_empty = None
    urgency = "unknown"
```

Output includes: `method: "rule-based"`, plus a note explaining that more usage logs are needed.

Both methods include expiry date checking and sustainability tips for non-eco items.

### Frontend: Prediction Card Enhancements

The `Predictions.jsx` component was updated to surface the richer forecast data:

- **Model badge** (`holt-linear`) shown alongside the method badge
- **Trend arrow** with colored background: red `↑ +15.2%` for increasing, green `↓ -8.1%` for decreasing, grey `→` for stable
- **Confidence indicator**: color-coded badge (green=high, yellow=medium, red=low)
- **Seasonality description**: purple text showing peak/trough days when weekly patterns are detected (e.g., "Usage peaks on Sat (+25%), dips on Tue (-15%)")
- **Forecast vs configured rate**: side-by-side comparison so users can see how actual consumption diverges from their configured rate

All new UI elements use `&&` conditionals — rule-based predictions (which lack these fields) render unchanged.

### Sustainability Score Algorithm

- **Eco-certified percentage**: (eco items / total items) * 100
- **Waste risk items**: Items expiring before they'll be used up
- **Estimated waste cost**: Sum of (remaining quantity * cost_per_unit) for waste-risk items
- **Carbon score**: eco_pct * 0.7 + waste_score * 0.3
- **Grade**: A (>=80), B (>=60), C (>=40), D (<40)

### What-If Scenario Simulator

Allows users to model procurement changes and see projected impact:

Supported scenarios:

- `reduce_usage`: Reduce an item's daily usage by X% (e.g., order less coffee)
- `reduce_order`: Reduce an item's current stock by X% (e.g., smaller next order)
- `switch_eco`: Switch a specific item to eco-certified (assumes 15% price premium)
- `all_eco`: Switch entire inventory to eco-certified

Output compares baseline vs projected metrics:

- Weekly waste cost
- Eco-certified percentage
- Carbon score (composite of eco + waste metrics)
- Weekly procurement cost

### Chat Co-Pilot (Rule-Based NLP)

Keyword-matching query handler for natural language questions:

- Waste queries: "reduce waste", "expiring", "throwing away"
- Cost queries: "cost", "expensive", "save money"
- Reorder queries: "running low", "stock", "reorder"
- Sustainability queries: "eco", "green", "carbon"
- Summary queries: "overview", "status"

Falls back to suggestion list for unrecognized queries.

## API Endpoints


| Method | Endpoint                  | Description                                                 |
| ------ | ------------------------- | ----------------------------------------------------------- |
| GET    | `/api/items`              | List items (supports `?search=`, `?category=`, `?urgency=`) |
| POST   | `/api/items`              | Create new item                                             |
| GET    | `/api/items/{id}`         | Get single item                                             |
| PUT    | `/api/items/{id}`         | Update item fields                                          |
| DELETE | `/api/items/{id}`         | Delete item                                                 |
| POST   | `/api/items/{id}/usage`   | Log usage (decrements quantity)                             |
| GET    | `/api/items/{id}/predict` | Get forecast/rule-based prediction for item                 |
| GET    | `/api/predictions`        | Get predictions for all items                               |
| GET    | `/api/sustainability`     | Get sustainability dashboard data                           |
| GET    | `/api/categories`         | List distinct categories                                    |
| POST   | `/api/what-if`            | Run what-if scenario simulation                             |
| POST   | `/api/chat`               | Natural language query to co-pilot                          |


## Input Validation

All input validation is handled by Pydantic models in `app.py`:

- `name`: Required, 1-200 characters
- `quantity`: Required, >= 0
- `unit`: Required, non-empty
- `daily_usage_rate`: >= 0 (defaults to 0)
- `cost_per_unit`: >= 0 (defaults to 0)
- `quantity_used` (usage log): Required, > 0
- `chat query`: Required, 1-500 characters
- `what-if action`: Required string, validated at service layer
- `reduce_pct`: 1-100 (defaults to 20)

Additional runtime validation:

- Usage cannot exceed current stock (returns 400)
- Item must exist for update/delete/usage operations (returns 404)
- At least one field required for update (returns 400)

## Error Handling Strategy


| Scenario                   | Response           | User Experience                         |
| -------------------------- | ------------------ | --------------------------------------- |
| Invalid input              | 422 + field errors | Form highlights invalid fields          |
| Item not found             | 404 + message      | "Item not found" alert                  |
| Insufficient stock         | 400 + current qty  | Shows available amount                  |
| Insufficient usage history | Automatic fallback | Seamless switch to rule-based with note |
| Database error             | 500                | Generic error message                   |


## Security Considerations

- No API keys required (fully local processing)
- `.env.example` provided for DB path configuration
- All user inputs validated via Pydantic before database operations
- Parameterized SQL queries prevent SQL injection
- No authentication (acceptable for MVP single-user scenario)
- CORS restricted to localhost development origins only (`localhost:5173`, `127.0.0.1:5173`)
- Static files served from pre-built React bundle

## Testing Strategy

22 tests covering:

- **Happy paths** (8): CRUD operations, search, predictions, sustainability scoring, local forecast with usage history, what-if simulator, chat waste query
- **Edge cases** (9): Empty names, negative quantities, nonexistent items, delete verification, stock overuse, zero usage rate predictions, forecast fallback without history, invalid what-if action, unknown chat query
- **Holt's method & seasonality** (5): Increasing trend detection, stable trend detection, seasonality detection with weekly pattern, no false-positive seasonality on uniform data, confidence field presence

Tests use an isolated temporary SQLite database (`tempfile.NamedTemporaryFile`) to avoid polluting production data. The `setup_db` fixture calls `init_db()` explicitly since FastAPI's `on_event("startup")` doesn't fire with `TestClient`.

## Future Enhancements

### Short-term (next sprint)

1. **Usage trend visualization**: Chart.js graphs showing consumption patterns from usage_log
2. **Seasonality-adjusted forecasts**: Use detected weekly indices to adjust Holt's per-day forecast (currently seasonality is informational — the runout estimate uses the Holt rate only)
3. **CSV bulk import**: Upload spreadsheets to add items in batch

### Medium-term

1. **Notification system**: Email/webhook alerts when forecast predicts critical levels
2. **Multi-user auth**: JWT-based authentication with role-based access
3. **Supplier directory**: Database of eco-certified suppliers with comparison

### Long-term

1. **Visual asset scanning**: Camera-based inventory using local vision models (e.g., YOLO)
2. **Anomaly detection**: Flag unusual consumption spikes using statistical outlier detection
3. **Carbon footprint tracking**: Integration with lifecycle assessment databases
4. **Mobile PWA**: Offline-capable progressive web app for warehouse use

## Learnings & Design Insights

### Why SES Was Insufficient

Simple exponential smoothing (SES) was the initial forecasting approach. It worked but had fundamental limitations that surfaced during testing:

1. **Trend lag**: SES produces a single smoothed level. When usage rises steadily (e.g., 2→3→4→5 units/day), the smoothed value trails behind because it blends new observations with stale history. With `alpha=0.3`, it takes many data points for the smoothed value to "catch up." Holt's method solves this by maintaining a separate trend component `T(t)` that explicitly tracks the rate of change.
2. **Trend detection was a hack**: The original SES implementation detected trends by comparing the average of the first half vs. the second half of the data window. This produced false positives on noisy data and missed gradual trends that spanned the entire window. Holt's `T(t)` provides trend as a first-class output of the model itself — `trend_pct = T/L * 100` — no post-hoc comparison needed.
3. **No confidence signal**: SES gave no indication of forecast reliability. A 3-day forecast and a 60-day forecast had equal weight. The MAE-based confidence scorer now explicitly flags low-data situations.

### Choosing Beta = 0.1 (Trend Damping)

The trend smoothing parameter `beta` controls how quickly the model reacts to changes in the rate of change. During testing:

- `beta = 0.3` (same as alpha) caused the trend to oscillate wildly on noisy data — a single high-usage day would swing the trend from "stable" to "increasing"
- `beta = 0.01` was too conservative — it took 30+ data points for the model to detect a genuine trend shift
- `beta = 0.1` strikes a balance: responds within ~7-10 days to a real trend change while filtering out daily noise

### Seasonality: Threshold Matters

The seasonality detector uses `stdev(seasonal_indices) > 0.10` as its detection threshold. Arriving at 0.10:

- At 0.05, random ±20% variance in seed data was enough to trigger false positives on items with no actual seasonal pattern
- At 0.20, the detector missed the real WEEKEND_SEASONAL pattern (which has a spread of ~0.85 to 1.25, stdev ≈ 0.14)
- 0.10 reliably separates the uniform-usage items from the genuinely seasonal ones, confirmed across 22 test cases

### Seed Data Duration: Why 60 Days

The original 14-day seed window was too short for reliable seasonality detection:

- 14 days = exactly 2 weekly cycles. With ±20% random variance, the seasonal signal could be masked by noise in any given week. The detector reported "medium" confidence at best.
- 60 days = 8+ full weekly cycles. The day-of-week averages converge toward the true seasonal multipliers, noise averages out, and the detector reports "high" confidence. This also gives Holt's model enough history for `beta=0.1` to properly converge on the trend.
- The trend factor was reduced from `+1% per day` (which would be +60% over 60 days — unrealistic) to `+0.2% per day` (up to +12% over 60 days), simulating a gentle long-term demand increase.

### Keeping Seasonality Informational

A key design decision was to keep seasonality **informational only** — the `days_until_empty` estimate still uses the Holt rate (L+T), not a seasonality-adjusted forecast. Reasons:

- Adjusting the forecast per-day would make the runout date fluctuate depending on which day the user checks it (checking on a Friday would show a different runout than checking on a Monday)
- For inventory reorder decisions, the smoothed average rate is more actionable than a day-specific rate
- The seasonal pattern is still surfaced in the UI (peak/trough days, multipliers) so users can make informed decisions about weekend staffing, ordering, etc.

### Test Design: Verifying Statistical Behavior

Testing statistical models requires care because exact outputs depend on floating-point accumulation:

- **Trend tests** use exaggerated slopes (1.0/day increase over 7 days) to ensure the trend_pct threshold (>10%) is clearly exceeded. The initial test used 0.5/day which produced a borderline trend_pct that sometimes fell below 10%.
- **Seasonality tests** use binary signals (5.0 weekdays, 10.0 weekends) rather than subtle multipliers to guarantee the stdev threshold is exceeded regardless of which days fall on which weekdays.
- **Confidence test** accepts `"low" or "medium"` rather than pinning to one value, because the MAE boost/penalty can shift the result when data is perfectly flat (MAE=0 → boost from low to medium).

---

## Industrial-Level Extensibility Roadmap

> **Version**: 1.0
> **Status**: Roadmap (not yet in execution)
> **Audience**: Engineering leads, architects, product stakeholders

### Executive Summary

This roadmap defines a three-phase plan to evolve the Green-Tech Inventory Co-Pilot from a working prototype into a production-grade, AI-powered, horizontally-scalable platform while preserving the core value proposition of sustainable inventory management.

**Phase 1 (Foundation)** makes the application production-ready: PostgreSQL, authentication, containerization, observability, and CI/CD.
**Phase 2 (Intelligence)** replaces keyword-matching NLP with LLM-powered chat (RAG + tool calling) and upgrades the prediction engine to a multi-model ML pipeline.
**Phase 3 (Scale)** adds multi-tenancy, horizontal scaling, event-driven architecture, and MLOps infrastructure.

### Target Architecture

```
                        +------------------+
                        |   CDN / Edge     |
                        |  (CloudFront)    |
                        +--------+---------+
                                 |
                        +--------+---------+
                        |  API Gateway /   |
                        |  Load Balancer   |
                        |  (Kong / Nginx)  |
                        +--------+---------+
                                 |
              +------------------+------------------+
              |                                     |
     +--------+---------+               +-----------+----------+
     |  Auth Service     |               |  WebSocket Gateway   |
     |  (OAuth2 / JWT)   |               |  (streaming chat)    |
     +--------+---------+               +-----------+----------+
              |                                     |
     +--------+-------------------------------------+----------+
     |                    FastAPI Application Cluster           |
     |                    (K8s Deployment, n replicas)          |
     |                                                         |
     |  +-------------+  +-------------+  +----------------+   |
     |  | Inventory   |  | AI/Chat     |  | Prediction     |   |
     |  | Service     |  | Service     |  | Service        |   |
     |  +------+------+  +------+------+  +-------+--------+   |
     |         |                |                  |            |
     |         |         +------+------+   +-------+--------+  |
     |         |         | LLM Client  |   | ML Pipeline    |  |
     |         |         | (Claude API)|   | (Prophet/LSTM/ |  |
     |         |         +------+------+   |  XGBoost)      |  |
     |         |                |          +-------+--------+  |
     |         |         +------+------+           |           |
     |         |         | Vector DB   |   +-------+--------+  |
     |         |         | (pgvector)  |   | Feature Store  |  |
     |         |         +-------------+   +----------------+  |
     +---------+-----------------------------------------------+
               |                    |
     +---------+--------+  +-------+--------+  +-------------+
     |  PostgreSQL       |  |  Redis          |  | RabbitMQ /  |
     |  (primary +       |  |  (cache +       |  | Celery      |
     |   read replicas)  |  |   sessions +    |  | (async jobs)|
     |                   |  |   rate limits)  |  |             |
     +-------------------+  +----------------+  +-------------+
               |
     +---------+--------+
     | Object Storage   |
     | (S3 / MinIO)     |
     | ML model artifacts|
     +------------------+
```

---

### Phase 1 -- Foundation (Weeks 1-8)

**Goal**: Make the application production-deployable, secure, and observable without changing user-facing features.

#### 1.1 Database: SQLite to PostgreSQL


| Attribute   | Current                              | Target                                    |
| ----------- | ------------------------------------ | ----------------------------------------- |
| Engine      | SQLite 3 (single file)               | PostgreSQL 16                             |
| ORM         | Raw `sqlite3` + context manager      | SQLAlchemy 2.0 async + Alembic migrations |
| Connection  | New connection per request           | Connection pool (asyncpg, pool_size=20)   |
| Schema mgmt | `CREATE TABLE IF NOT EXISTS` in code | Alembic versioned migrations              |


**Rationale**: SQLite cannot handle concurrent writes from multiple workers. PostgreSQL provides ACID transactions, connection pooling, full-text search, and the `pgvector` extension needed for Phase 2 RAG.

**Key changes to `database.py`**:

- Replace `get_db()` context manager with SQLAlchemy async session factory
- Convert raw SQL strings in `services/inventory_service.py` to SQLAlchemy ORM models
- Add `alembic/` directory with initial migration generated from current schema
- Move `seed_from_json()` into a one-time migration or management command
- Add `pgvector` extension in the initial migration (future-proofing for Phase 2)

#### 1.2 Authentication and Authorization


| Attribute     | Current | Target                                         |
| ------------- | ------- | ---------------------------------------------- |
| Auth          | None    | OAuth2 + JWT (RS256)                           |
| Authorization | None    | RBAC (admin, manager, viewer)                  |
| Session       | None    | Stateless JWT with Redis-backed refresh tokens |


**Technology**: `python-jose` for JWT, `passlib` for password hashing, OAuth2 password flow via FastAPI's built-in `OAuth2PasswordBearer`. External IdP support (Google, Azure AD) via `authlib`.

**Key changes to `app.py`**:

- New `services/auth_service.py` with user registration, login, token refresh
- New `users` table (id, email, hashed_password, role, tenant_id, created_at)
- FastAPI dependency `get_current_user` injected into all route handlers
- Role-based guards: viewers can read, managers can CRUD, admins can manage users
- Frontend: login page, token storage in httpOnly cookie, `api.js` sends Authorization header

#### 1.3 Containerization and Orchestration


| Attribute | Current                    | Target                               |
| --------- | -------------------------- | ------------------------------------ |
| Runtime   | Bare `uvicorn` process     | Docker container on K8s              |
| Frontend  | `vite dev` or static mount | Nginx container serving built assets |
| DB        | Local file                 | Managed PostgreSQL (or StatefulSet)  |


**Key artifacts**:

- `Dockerfile` (multi-stage: Python deps + frontend build)
- `docker-compose.yml` (local dev: api, postgres, redis, frontend)
- `k8s/` directory: Deployment, Service, Ingress, ConfigMap, Secret manifests
- Helm chart for parameterized deployments across environments

#### 1.4 API Gateway and Rate Limiting


| Attribute     | Current                          | Target                                          |
| ------------- | -------------------------------- | ----------------------------------------------- |
| Gateway       | None (FastAPI serves everything) | Kong or Nginx Ingress                           |
| Rate limiting | None                             | Redis-backed token bucket (100 req/min default) |
| CORS          | Hardcoded localhost origins      | Configurable per environment                    |


**Key changes**:

- Move CORS configuration to environment variables
- Add `slowapi` middleware for per-user rate limiting backed by Redis
- API versioning: prefix all routes with `/api/v1/`
- Health check endpoint: `GET /health` (DB connectivity, Redis ping)

#### 1.5 Caching


| Attribute | Current | Target              |
| --------- | ------- | ------------------- |
| Cache     | None    | Redis 7 (TTL-based) |


**Strategy**:

- Cache `GET /api/v1/items` responses (30s TTL, invalidated on write)
- Cache sustainability scores (60s TTL)
- Cache prediction results (5min TTL, invalidated on usage log)
- Session/refresh token storage in Redis

#### 1.6 CI/CD Pipeline

**Platform**: GitHub Actions (or GitLab CI).

**Pipeline stages**:

1. **Lint**: `ruff` (Python), `eslint` (JS)
2. **Test**: `pytest` with PostgreSQL service container, Vitest for frontend
3. **Build**: Docker multi-stage image
4. **Security**: `trivy` container scan, `bandit` for Python security
5. **Deploy**: Staging auto-deploy on merge to `main`, production via manual approval

#### 1.7 Observability


| Signal             | Tool                                                    | Integration                                                                     |
| ------------------ | ------------------------------------------------------- | ------------------------------------------------------------------------------- |
| Structured logging | `structlog`                                             | JSON logs to stdout, collected by Fluentd/Loki                                  |
| Metrics            | Prometheus client (`prometheus-fastapi-instrumentator`) | Request latency, error rates, prediction model usage                            |
| Tracing            | OpenTelemetry SDK                                       | Distributed traces across API -> service -> DB                                  |
| Dashboards         | Grafana                                                 | Pre-built dashboards for API health, prediction accuracy, sustainability trends |
| Alerting           | Grafana Alerting or PagerDuty                           | Critical stock alerts, error rate spikes, prediction drift                      |


**Key changes**:

- Replace all `print()` and bare `except: pass` with structured logging
- Add request-id middleware for trace correlation
- Instrument database queries with span timing
- Add `/metrics` endpoint for Prometheus scraping

#### 1.8 Frontend Modernization


| Attribute        | Current                        | Target                                        |
| ---------------- | ------------------------------ | --------------------------------------------- |
| State management | `useState` + prop drilling     | Zustand (lightweight, no boilerplate)         |
| API layer        | Raw `fetch` with hardcoded URL | Axios instance + React Query (TanStack Query) |
| Styling          | Vanilla CSS (`index.css`)      | Tailwind CSS 4 or CSS Modules                 |
| Routing          | Tab switching via state        | React Router v7 with URL-based navigation     |


**Rationale**: Zustand over Redux because the app's state graph is shallow (items, predictions, sustainability). React Query handles caching, refetching, and optimistic updates, eliminating most manual `useEffect` data fetching. URL-based routing enables deep-linking to specific tabs/items.

---

### Phase 2 -- Intelligence (Weeks 9-16)

**Goal**: Replace rule-based NLP with LLM-powered conversational AI and upgrade the prediction engine to a multi-model ML pipeline.

#### 2.1 LLM-Powered Chat System


| Attribute | Current                                         | Target                                                  |
| --------- | ----------------------------------------------- | ------------------------------------------------------- |
| NLP       | Keyword matching (5 intents) in `ai_service.py` | Claude API (claude-sonnet-4-20250514) with tool calling |
| Context   | None -- stateless                               | RAG over inventory data + conversation memory           |
| Response  | Static JSON templates                           | Streaming natural language + structured data            |
| Fallback  | Suggestion list                                 | Graceful degradation to existing rule-based engine      |


**Architecture**:

```
User query
    |
    v
[Intent Classifier]  -- fast local check: simple lookup or complex question?
    |          |
    |      [Simple]  --> Rule-based engine (existing ai_service.py, zero-cost fast path)
    |
 [Complex]
    |
    v
[RAG Pipeline]
    |-- 1. Embed query (voyage-3 or local all-MiniLM-L6-v2)
    |-- 2. Retrieve top-k inventory context from pgvector
    |-- 3. Fetch live metrics (sustainability score, predictions for critical items)
    |-- 4. Assemble system prompt + context + user query
    |
    v
[Claude API]  -- tool_use enabled
    |-- Tools: query_inventory, get_prediction, run_what_if, get_sustainability
    |-- System prompt: domain expert persona, output format instructions
    |-- Streaming: SSE to frontend
    |
    v
[Response + tool results streamed to frontend]
```

**Tool calling schema** (registered with Claude):

- `query_inventory(search?, category?, urgency?)` -- wraps `list_items()`
- `get_item_prediction(item_id)` -- wraps `local_forecast_prediction()`
- `get_all_predictions()` -- wraps `predict_all()`
- `get_sustainability_score()` -- wraps `calculate_sustainability_score()`
- `run_what_if(action, item_id?, reduce_pct?)` -- wraps `simulate_what_if()`
- `log_usage(item_id, quantity)` -- wraps `log_usage()` (with user confirmation)

**Conversation memory**:

- New `conversations` table: (id, user_id, created_at)
- New `messages` table: (id, conversation_id, role, content, tool_calls_json, token_count, created_at)
- Sliding window: last 20 messages included in context, older messages summarized
- Per-conversation token budget: 50K input tokens max, automatic summarization beyond threshold

**Cost management**:

- Intent classifier routes simple queries to the free rule-based engine (expected 40-60% of queries)
- Token budget per user per day (configurable): default 200K tokens
- Model tier selection: Haiku for simple clarifications, Sonnet for complex analysis
- Response caching: identical queries within 5 minutes return cached response
- Admin dashboard showing token usage by user and query category

**Streaming**:

- New `POST /api/v1/chat/stream` endpoint returning Server-Sent Events (SSE)
- Frontend: `EventSource` or `fetch` with `ReadableStream` reader
- Tool call results injected mid-stream as structured JSON blocks

**Prompt engineering patterns**:

- System prompt defines persona: "You are a sustainability-focused inventory analyst..."
- Inventory context injected as structured XML blocks for reliable parsing
- Output format instructions: "Always include actionable recommendations. When suggesting reorders, include specific quantities."
- Few-shot examples for common query patterns embedded in system prompt
- Guard rails: refuse out-of-domain queries, never fabricate inventory data

#### 2.2 RAG Pipeline


| Component        | Technology                                                                  | Rationale                                         |
| ---------------- | --------------------------------------------------------------------------- | ------------------------------------------------- |
| Vector store     | pgvector (PostgreSQL extension)                                             | Co-located with primary DB, no separate service   |
| Embedding model  | Voyage-3 API or local `all-MiniLM-L6-v2`                                    | Voyage for quality, MiniLM for cost/latency       |
| Chunk strategy   | Per-item document (name + category + supplier + notes + recent predictions) | Small corpus; full-item granularity is sufficient |
| Indexing trigger | On item create/update/delete, on daily prediction refresh                   | Event-driven re-embedding                         |


**Document schema per item**:

```
Item: {name}
Category: {category} | Supplier: {supplier}
Stock: {quantity} {unit} | Usage: {daily_usage_rate}/day
Eco-certified: {yes/no} | Expiry: {expiry_date or "N/A"}
Prediction: {days_until_empty} days remaining, trend {trend}
Notes: {notes}
```

For a 10-50 item inventory, the entire corpus fits in a single context window. RAG becomes essential when the inventory scales to hundreds or thousands of items (Phase 3 multi-tenancy).

#### 2.3 ML Prediction Pipeline


| Attribute  | Current                                          | Target                                                |
| ---------- | ------------------------------------------------ | ----------------------------------------------------- |
| Model      | Single (Holt's linear) in `prediction_engine.py` | Ensemble: Prophet + XGBoost + LSTM                    |
| Features   | Usage history only                               | Usage + holidays + weather + day-of-week + promotions |
| Selection  | None                                             | Automated backtesting with best-model selection       |
| Confidence | Heuristic (data points + MAE)                    | Statistical confidence intervals (80%/95%)            |
| Anomalies  | None                                             | Z-score + isolation forest                            |


**Model registry** (new `models` table):

- model_id, item_id, model_type, hyperparameters_json, trained_at, mae, mape, is_active
- Only one model active per item at any time
- Historical models retained for comparison

**Ensemble strategy**:

1. **Prophet** (primary): Best for items with strong seasonality and trend. Handles holidays natively. Used when data >= 30 days.
2. **XGBoost** (tabular features): Best when external features (weather, events) are available. Feature vector: day_of_week, month, is_holiday, temperature, lag_1, lag_7, rolling_mean_7, rolling_std_7.
3. **LSTM** (deep learning): Best for items with complex non-linear patterns. Used when data >= 90 days. PyTorch implementation with 2-layer LSTM, hidden_size=64.
4. **Holt's linear** (lightweight fallback): Retained for items with < 14 days of data. Zero external dependencies.

**Automated model selection**:

- Nightly batch job trains all eligible models per item
- Walk-forward backtesting: train on days 1..N-14, test on days N-14..N
- Selection metric: weighted MAPE (recent errors weighted 2x)
- Ensemble option: weighted average of top-2 models (weights = inverse MAPE)

**Feature engineering pipeline**:


| Feature                         | Source                      | Update Frequency |
| ------------------------------- | --------------------------- | ---------------- |
| Usage history (lag 1-14)        | `usage_log` table           | Real-time        |
| Day of week, month, quarter     | Derived                     | Static           |
| Rolling mean/std (7d, 14d, 30d) | `usage_log` table           | Daily            |
| Is holiday                      | `holidays` Python package   | Yearly           |
| Temperature (local)             | OpenWeatherMap API          | Daily            |
| Promotional events              | New `events` table (manual) | On entry         |
| Item category embedding         | Derived from category       | On change        |


**Anomaly detection**:

- Real-time: Z-score on incoming usage logs (flag if |z| > 3 relative to 30-day rolling stats)
- Batch: Isolation forest trained on multi-dimensional feature vectors (usage, cost, time-since-last-usage)
- Anomalies surface as alerts in the frontend and as context in the chat system

**Demand sensing** (short-horizon):

- For items with < 3 days of remaining stock, switch from daily forecasts to 6-hour granularity
- Use most recent 48 hours of usage data weighted by recency
- Push notifications via WebSocket when demand-sensed runout is < 24 hours

**Confidence intervals**:

- Prophet: native 80%/95% prediction intervals via MCMC
- XGBoost: quantile regression (predict 10th, 50th, 90th percentiles)
- LSTM: MC Dropout (100 forward passes, compute empirical intervals)
- Frontend: shaded area on prediction charts showing confidence bands

**Backtesting framework**:

- New `backtests` table: (id, item_id, model_type, train_end_date, test_mae, test_mape, created_at)
- Walk-forward with expanding window: minimum 14 days train, 7 days test, step by 7 days
- Automated comparison report: summary of model performance per item per quarter
- Accessible via admin API: `GET /api/v1/admin/backtests?item_id=X`

---

### Phase 3 -- Scale (Weeks 17-24)

**Goal**: Multi-tenancy, horizontal scaling, event-driven architecture, and MLOps.

#### 3.1 Multi-Tenancy


| Attribute  | Current                 | Target                                 |
| ---------- | ----------------------- | -------------------------------------- |
| Tenancy    | Single-user, single-org | Schema-per-tenant (PostgreSQL schemas) |
| Isolation  | N/A                     | Row-level security + schema isolation  |
| Onboarding | Seed script             | Self-service tenant registration       |


**Strategy**: Schema-per-tenant in PostgreSQL. Each tenant gets their own schema (e.g., `tenant_acme.items`, `tenant_acme.usage_log`) with identical table structures. This provides strong data isolation while keeping a single database cluster.

**Key changes**:

- New `tenants` table in `public` schema: (id, slug, name, plan, created_at)
- Middleware extracts tenant from JWT claims, sets `search_path` on connection
- All service functions receive tenant context implicitly via request-scoped DB session
- Tenant-aware Redis cache keys: `tenant:{slug}:items:list`

#### 3.2 Horizontal Scaling


| Component   | Strategy                                                    |
| ----------- | ----------------------------------------------------------- |
| API servers | Stateless FastAPI behind K8s HPA (CPU/request-rate based)   |
| Database    | Primary + 2 read replicas, pgBouncer for connection pooling |
| Redis       | Redis Cluster (3 masters + 3 replicas)                      |
| ML training | Separate worker pool (K8s Job or Celery workers)            |
| LLM calls   | Async with circuit breaker (tenacity + httpx)               |


**Async operations via message queue**:

- **RabbitMQ** (or Redis Streams for simplicity) as message broker
- **Celery** workers for: ML model training, batch predictions, report generation, embedding updates
- API returns job ID immediately; frontend polls or receives WebSocket notification on completion

**Operations offloaded to queue**:

1. Nightly model retraining (all items, all tenants)
2. Bulk CSV import processing
3. Embedding re-indexing after batch item updates
4. Sustainability report PDF generation
5. Anomaly detection batch scan

#### 3.3 MLOps Infrastructure


| Capability             | Tool                                | Purpose                                                   |
| ---------------------- | ----------------------------------- | --------------------------------------------------------- |
| Experiment tracking    | MLflow                              | Log hyperparameters, metrics, artifacts per training run  |
| Model registry         | MLflow Model Registry               | Version models, stage transitions (staging -> production) |
| Model serving          | FastAPI (in-process) or Triton      | Low-latency inference                                     |
| A/B testing            | Custom (traffic split by item hash) | Compare model versions on live traffic                    |
| Drift detection        | Evidently AI                        | Monitor feature and prediction distribution shifts        |
| Pipeline orchestration | Prefect or Airflow                  | Schedule training, backtesting, drift checks              |


**Model versioning**:

- Every trained model stored as an artifact in S3/MinIO with MLflow run ID
- `model_deployments` table: (id, item_id, model_version, deployed_at, traffic_pct, is_champion)
- Champion/challenger pattern: new model gets 10% traffic for 7 days, promoted if MAPE improves

**Drift detection**:

- Daily job compares last-7-day feature distributions against training distribution (PSI > 0.2 triggers alert)
- Prediction drift: compare predicted vs actual usage (rolling 7-day MAPE > 2x training MAPE triggers retraining)
- Alerts feed into chat system: "Model drift detected for Fair-Trade Coffee Beans -- retraining recommended"

#### 3.4 Event-Driven Architecture

Move from request-response to event-sourced patterns for key flows:


| Event                  | Producer           | Consumers                                                |
| ---------------------- | ------------------ | -------------------------------------------------------- |
| `item.created`         | inventory_service  | embedding_indexer, prediction_scheduler                  |
| `item.updated`         | inventory_service  | embedding_indexer, cache_invalidator                     |
| `item.deleted`         | inventory_service  | embedding_indexer, cache_invalidator, prediction_cleanup |
| `usage.logged`         | inventory_service  | prediction_updater, anomaly_detector, cache_invalidator  |
| `prediction.completed` | prediction_service | notification_service, embedding_indexer                  |
| `model.trained`        | ml_pipeline        | model_registry, drift_detector                           |
| `alert.triggered`      | anomaly_detector   | notification_service, chat_context_builder               |


**Implementation**: Start with an in-process event bus (Python `asyncio` queues) in Phase 1, migrate to RabbitMQ/Kafka in Phase 3 as message volume grows.

#### 3.5 Real-Time Updates


| Attribute   | Current               | Target                           |
| ----------- | --------------------- | -------------------------------- |
| Updates     | Manual refresh        | WebSocket push                   |
| Chat        | Request-response JSON | SSE streaming                    |
| Predictions | On-demand fetch       | Push on anomaly/threshold breach |


**WebSocket channels** (per tenant):

- `inventory.updates` -- item quantity changes
- `alerts.critical` -- stock critical, anomaly detected, model drift
- `predictions.refresh` -- new predictions available

---

### Migration Strategy

The migration from current state to target follows a strict incremental approach. At no point does the system become non-functional.

#### Step 1: Introduce abstraction layers (Week 1-2)

**Before changing any infrastructure**, refactor the code to use abstractions:

1. Create a `repositories/` layer between services and database
  - `ItemRepository` with methods matching current `inventory_service.py` functions
  - Initially backed by SQLite (existing `get_db()`)
  - Services call repository methods instead of raw SQL
2. Create a `config.py` using Pydantic `BaseSettings` for all environment-dependent values
  - DB connection string, CORS origins, Redis URL, LLM API key, etc.
3. Add API versioning: mount all current routes under `/api/v1/`
4. Add the health check endpoint

**Zero downtime**: Existing behavior unchanged. All tests pass against same SQLite backend.

#### Step 2: Database migration (Week 2-4)

1. Add SQLAlchemy ORM models mirroring current SQLite schema
2. Set up Alembic with initial migration
3. Write a data migration script: SQLite -> PostgreSQL
4. Switch `ItemRepository` implementation to SQLAlchemy
5. Run existing test suite against PostgreSQL (GitHub Actions with postgres service container)
6. Deploy with `DB_TYPE` environment variable: `sqlite` (default) or `postgres`

**Rollback**: Flip `DB_TYPE` back to `sqlite`. Both implementations coexist.

#### Step 3: Auth and infrastructure (Week 3-6)

1. Add auth service, user model, JWT middleware
2. Existing routes work without auth in development (guard disabled when `AUTH_DISABLED=true`)
3. Create Docker Compose for local development
4. Create Dockerfile, push to container registry
5. Set up CI pipeline (lint, test, build, scan)
6. Deploy to staging Kubernetes cluster

**Rollback**: Auth middleware is a FastAPI dependency; removing it from routes restores open access.

#### Step 4: Intelligence upgrades (Week 7-12)

1. Add LLM integration behind a feature flag (`CHAT_MODE=rule-based|llm`)
2. Rule-based engine remains the default; LLM mode opt-in per tenant
3. Add ML models one at a time: Prophet first (most similar to Holt's), then XGBoost, then LSTM
4. Each model registered in model registry; Holt's remains active until new model proves superior via backtesting
5. RAG pipeline added alongside existing chat -- intent classifier routes between them

**Rollback**: Feature flags disable any new capability independently.

#### Step 5: Scale infrastructure (Week 13-20)

1. Add Redis caching (read-through pattern, services unaware of cache layer)
2. Add Celery workers for async operations
3. Add multi-tenancy schema routing
4. Enable horizontal pod autoscaling
5. Deploy MLOps pipeline (MLflow, drift detection)

**Rollback**: Each component is independently deployable and removable.

#### Dependency Graph

```
Step 1 (Abstractions)
  |
  v
Step 2 (PostgreSQL) --------+
  |                          |
  v                          v
Step 3 (Auth + Docker)    Step 4a (LLM Chat)
  |                          |
  v                          v
Step 4b (ML Pipeline)     Step 4c (RAG -- needs pgvector from Step 2)
  |                          |
  +----------+---------------+
             |
             v
         Step 5 (Scale)
```

---

### Risk Register


| Risk                                            | Likelihood | Impact   | Mitigation                                                                                                                           |
| ----------------------------------------------- | ---------- | -------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| LLM API costs exceed budget                     | Medium     | High     | Intent classifier diverts 40-60% of queries to free rule-based engine; per-user token budgets; Haiku for simple queries              |
| PostgreSQL migration data loss                  | Low        | Critical | Dual-write period during migration; SHA-256 checksums on migrated records; automated rollback script                                 |
| ML model produces worse predictions than Holt's | Medium     | Medium   | Champion/challenger pattern; Holt's remains active until new model wins backtesting by >5% MAPE improvement                          |
| Multi-tenancy data leakage                      | Low        | Critical | Schema-per-tenant isolation; automated integration tests that verify cross-tenant queries return empty; security audit               |
| Kubernetes complexity overwhelms small team     | Medium     | Medium   | Start with Docker Compose for staging; K8s only for production; use managed K8s (EKS/GKE)                                            |
| Vendor lock-in on LLM provider                  | Low        | Medium   | Abstract LLM client behind interface; tool schemas are model-agnostic; swap Claude for OpenAI or local model without service changes |


---

### Decision Log


| Decision         | Chosen                      | Alternatives Considered                 | Rationale                                                                                          |
| ---------------- | --------------------------- | --------------------------------------- | -------------------------------------------------------------------------------------------------- |
| ORM              | SQLAlchemy 2.0 async        | Tortoise ORM, raw asyncpg               | Industry standard, Alembic migrations, team familiarity                                            |
| Vector DB        | pgvector                    | Pinecone, Weaviate, Qdrant              | Co-located with primary DB; small corpus does not justify a separate vector service                |
| LLM              | Claude API (Sonnet)         | OpenAI GPT-4o, local LLaMA              | Superior tool calling reliability; Anthropic alignment with sustainability mission                 |
| ML framework     | Prophet + XGBoost + PyTorch | statsmodels only, TensorFlow            | Prophet handles seasonality natively; XGBoost for tabular features; PyTorch for LSTM flexibility   |
| State management | Zustand                     | Redux Toolkit, Jotai, Context API       | Minimal boilerplate for shallow state graph; no provider wrappers needed                           |
| Message queue    | RabbitMQ                    | Kafka, Redis Streams                    | Right-sized for expected throughput; Kafka is overkill until event volume exceeds 10K/min          |
| Multi-tenancy    | Schema-per-tenant           | Row-level security, database-per-tenant | Balances isolation strength vs operational overhead; easier migration path from single-tenant      |
| MLOps            | MLflow                      | Weights & Biases, custom                | Open-source, self-hostable, integrates with all three ML frameworks                                |
| Caching          | Redis                       | Memcached, in-process LRU               | Needed for sessions, rate limiting, and pub/sub (WebSocket fan-out) beyond just caching            |
| CI/CD            | GitHub Actions              | GitLab CI, Jenkins                      | Native GitHub integration; matrix builds for Python + Node; free tier sufficient for initial scale |


