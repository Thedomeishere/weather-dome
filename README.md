# Weather-Dome

Weather impact prediction dashboard for Con Edison of NY and Orange & Rockland (O&R) overhead electrical system territories.

## Overview

Weather-Dome aggregates weather data from multiple sources (NWS, OpenWeatherMap, Visual Crossing), runs impact prediction models, and presents results in an interactive React dashboard with territory maps.

### Impact Models

- **Outage Risk** - Wind, ice, lightning, precipitation scoring with synergy bonuses
- **Vegetation Risk** - Seasonal foliage factor, soil saturation, ice loading
- **Load Forecast** - Temperature-driven U-curve demand model with time-of-day factors
- **Equipment Stress** - Transformer heat and line sag risk assessment
- **Crew Deployment** - Staffing recommendations with mutual aid and pre-staging flags

### Territory Coverage

- **Con Edison**: Manhattan, Bronx, Brooklyn, Queens, Staten Island, Westchester (6 zones)
- **O&R**: Orange, Rockland, Sullivan counties + NJ portions (5 zones)

## Quick Start

### Backend

```bash
cd backend
pip install -e ".[dev]"
cp ../.env.example .env  # Edit with your API keys (NWS requires no key)
uvicorn app.main:app --reload
```

Backend runs on http://localhost:8000. Swagger docs at http://localhost:8000/docs.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend runs on http://localhost:5173 with API proxy to backend.

## Configuration

Copy `.env.example` to `backend/.env` and configure:

- `OWM_API_KEY` - OpenWeatherMap One Call API key (optional)
- `VISUAL_CROSSING_API_KEY` - Visual Crossing API key (optional)
- NWS API is free and requires no key
- All impact thresholds are configurable via environment variables

## Architecture

```
Weather APIs ─→ Scheduled Ingest (15 min) ─→ Aggregation (conservative merge)
                                                    │
                                              Impact Models
                                                    │
                                              SQLite DB ─→ REST API ─→ React Dashboard (60s poll)
```

## Tech Stack

- **Backend**: Python 3.12, FastAPI, SQLAlchemy (SQLite), httpx, APScheduler
- **Frontend**: React 18, TypeScript, Vite, Leaflet, TanStack React Query, Recharts, Tailwind CSS

## API Endpoints

| Endpoint | Description |
|---|---|
| `GET /api/v1/dashboard/?territory=CONED\|OR` | Composite dashboard data |
| `GET /api/v1/weather/current/` | Current conditions all zones |
| `GET /api/v1/weather/forecast/{zone_id}` | 48-hour forecast |
| `GET /api/v1/weather/alerts/` | Active NWS alerts |
| `GET /api/v1/impact/` | All impact assessments |
| `GET /api/v1/impact/{zone_id}` | Zone impact detail |
| `GET /api/v1/territory/zones/` | Zone listing |
| `GET /api/v1/territory/geojson/{territory}` | Territory GeoJSON |
| `GET /health` | Health check |
