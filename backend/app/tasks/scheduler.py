"""APScheduler setup for periodic weather ingest, impact computation, and outage ingest."""

import asyncio
import logging

from apscheduler.schedulers.background import BackgroundScheduler

from app.config import settings

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def _run_weather_ingest():
    from app.services.weather_ingest import ingest_all_zones
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(ingest_all_zones())
    except Exception as e:
        logger.error("Weather ingest job failed: %s", e)
    finally:
        loop.close()


def _run_impact_compute():
    from app.services.impact_engine import compute_all_zones
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(compute_all_zones())
    except Exception as e:
        logger.error("Impact compute job failed: %s", e)
    finally:
        loop.close()


def _run_outage_ingest():
    from app.services.outage_ingest import ingest_outages
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(ingest_outages())
    except Exception as e:
        logger.error("Outage ingest job failed: %s", e)
    finally:
        loop.close()


def start_scheduler():
    global _scheduler
    _scheduler = BackgroundScheduler()

    _scheduler.add_job(
        _run_weather_ingest,
        "interval",
        minutes=settings.weather_ingest_interval,
        id="weather_ingest",
        name="Weather data ingestion",
        max_instances=1,
    )

    _scheduler.add_job(
        _run_impact_compute,
        "interval",
        minutes=settings.impact_compute_interval,
        id="impact_compute",
        name="Impact model computation",
        max_instances=1,
    )

    _scheduler.add_job(
        _run_outage_ingest,
        "interval",
        minutes=settings.ods_ingest_interval,
        id="outage_ingest",
        name="Outage data ingestion",
        max_instances=1,
    )

    _scheduler.start()
    logger.info(
        "Scheduler started: weather every %d min, impact every %d min, outages every %d min",
        settings.weather_ingest_interval,
        settings.impact_compute_interval,
        settings.ods_ingest_interval,
    )


def stop_scheduler():
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
        _scheduler = None
