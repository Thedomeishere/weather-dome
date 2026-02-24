# Weather-Dome Project Guide

## Project Structure
```
weather-dome/
├── backend/                    # Python FastAPI backend
│   ├── app/
│   │   ├── config.py          # Pydantic Settings (env vars)
│   │   ├── database.py        # SQLAlchemy engine/session (SQLite)
│   │   ├── main.py            # FastAPI app with CORS + lifespan
│   │   ├── models/            # SQLAlchemy ORM models
│   │   ├── schemas/           # Pydantic request/response schemas
│   │   ├── services/          # Business logic (weather clients, impact models)
│   │   ├── routers/           # FastAPI route handlers
│   │   ├── tasks/             # APScheduler background tasks
│   │   └── territory/         # Zone/territory definitions
│   ├── tests/
│   └── pyproject.toml
├── frontend/                   # React + TypeScript + Vite
│   ├── src/
│   │   ├── api/               # Axios client + TypeScript types
│   │   ├── hooks/             # React Query hooks
│   │   └── components/        # React components (map, weather, impact, crew)
│   └── package.json
├── data/                       # GeoJSON and zone mappings
└── .env.example
```

## Key Conventions
- Backend uses Python 3.12+ with type hints
- All weather data uses imperial units (°F, mph, inches)
- Impact scores are 0-100 with levels: Low (<25), Moderate (<50), High (<75), Extreme (≥75)
- Conservative weather merge: max wind/ice/precip across sources
- Frontend polls `/api/v1/dashboard/` every 60 seconds

## Running
- Backend: `cd backend && uvicorn app.main:app --reload` (port 8000)
- Frontend: `cd frontend && npm run dev` (port 5173, proxies /api to 8000)
- Tests: `cd backend && pytest`

## Territory IDs
- `CONED` - Con Edison (6 zones: MAN, BRX, BKN, QNS, SI, WST)
- `OR` - Orange & Rockland (5 zones: ORA, ROC, SUL, BER, SSX)
