from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    from app.tasks.scheduler import start_scheduler, stop_scheduler
    start_scheduler()
    # Run initial ingest on startup
    import asyncio
    from app.services.weather_ingest import ingest_all_zones
    from app.services.impact_engine import compute_all_zones
    asyncio.create_task(_initial_ingest())
    yield
    stop_scheduler()


async def _initial_ingest():
    """Run weather ingest + impact compute on startup."""
    import logging
    logger = logging.getLogger(__name__)
    try:
        from app.services.weather_ingest import ingest_all_zones
        from app.services.impact_engine import compute_all_zones
        logger.info("Running initial weather ingest...")
        await ingest_all_zones()
        logger.info("Running initial impact compute...")
        await compute_all_zones()
        logger.info("Initial data load complete")
    except Exception as e:
        logger.error("Initial ingest failed: %s", e)


app = FastAPI(
    title="Weather-Dome",
    description="Weather impact prediction for Con Edison & O&R territories",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.routers import dashboard, weather, impact, territory  # noqa: E402

app.include_router(dashboard.router, prefix="/api/v1")
app.include_router(weather.router, prefix="/api/v1")
app.include_router(impact.router, prefix="/api/v1")
app.include_router(territory.router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/api/v1/admin/ingest")
async def trigger_ingest():
    """Manually trigger weather ingest + impact recompute."""
    from app.services.weather_ingest import ingest_all_zones
    from app.services.impact_engine import compute_all_zones
    await ingest_all_zones()
    await compute_all_zones()
    return {"status": "ingest_complete"}
