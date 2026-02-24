# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Backend
```bash
cd backend && uvicorn app.main:app --reload          # Dev server (port 8000)
cd backend && pytest                                   # All tests
cd backend && pytest tests/test_impact.py -v          # Single test file
cd backend && pytest tests/test_impact.py::test_name  # Single test
```

### Frontend
```bash
cd frontend && npm run dev      # Dev server (port 5173, proxies /api to :8000)
cd frontend && npm run build    # TypeScript check + Vite production build
```

Python virtual environment: `source .venv/bin/activate` (from project root).

## Architecture

### Data Pipeline
Weather data flows through a scheduled pipeline: **3 weather sources → conservative aggregation → 5 impact models → in-memory cache + SQLite → REST API → React frontend**.

APScheduler runs two background jobs on startup:
- **Weather ingest** (every 15m): Fetches current/forecast/alerts from NWS, OpenWeatherMap, and Visual Crossing in parallel for all 11 zones. Aggregates conservatively (max for wind/ice/precip, min for visibility, weighted avg for temp/pressure).
- **Impact compute** (every 30m): Runs 5 independent models per zone, combines into weighted overall score (outage 35%, load 20%, vegetation 15%, equipment 15%, crew 15%).

### Backend (`backend/app/`)
- **`services/`** — Core business logic. Weather clients (`nws_client.py`, `owm_client.py`, `visual_crossing_client.py`) each implement `fetch_current()`, `fetch_forecast()`, `fetch_alerts()`. `weather_aggregator.py` merges sources. `impact_engine.py` orchestrates 5 models from `services/` (outage_risk, vegetation_risk, load_forecast, equipment_stress, crew_deployment).
- **`routers/`** — Four routers mounted at `/api/v1/`: dashboard (composite endpoint), weather, impact, territory.
- **`territory/definitions.py`** — Zone definitions with coordinates, NWS zone IDs, gridpoints, and peak load shares. 11 zones: 6 ConEd + 5 O&R.
- **`tasks/scheduler.py`** — APScheduler setup wrapping async ingest/compute functions.
- **`config.py`** — Pydantic Settings loading from `.env`. Configurable thresholds for wind/ice/temp, scheduler intervals, territory capacities.

### Frontend (`frontend/src/`)
- **`api/client.ts`** — Axios client. Main call is `fetchDashboard(territory)` → `GET /api/v1/dashboard/`.
- **`hooks/useWeatherData.ts`** — React Query hooks. `useDashboard()` polls every 60s.
- **`components/`** — Organized by domain: `map/` (Leaflet), `weather/` (conditions + alerts), `impact/` (risk cards + forecast chart), `crew/` (deployment recommendations).

### Key Data Flow
The dashboard endpoint (`routers/dashboard.py`) assembles everything: reads in-memory caches for weather/alerts/impacts, computes territory overview (max risk, total outages, peak load), and returns a single `DashboardResponse`. Frontend `App.tsx` calls this and distributes data to child components.

## Conventions
- All weather in imperial units (°F, mph, inches)
- Impact scores 0–100; levels: Low (<25), Moderate (<50), High (<75), Extreme (≥75)
- Conservative weather merge: max wind/ice/precip across sources (safety-first)
- No migration framework — `Base.metadata.create_all()` on startup (SQLite)
- pytest with `asyncio_mode = "auto"` for async tests
- Frontend uses Tailwind CSS, Recharts for charts, Leaflet for maps

## Territory IDs
- `CONED` — Con Edison (6 zones: MAN, BRX, BKN, QNS, SI, WST)
- `OR` — Orange & Rockland (5 zones: ORA, ROC, SUL, BER, SSX)
