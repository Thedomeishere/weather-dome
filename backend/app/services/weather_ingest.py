"""Orchestrates fetching weather data from all sources for all zones."""

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.weather import WeatherObservation, WeatherForecast, WeatherAlert
from app.schemas.weather import WeatherConditions, ZoneForecast, AlertSchema
from app.services import nws_client, owm_client, visual_crossing_client
from app.services.weather_aggregator import aggregate_current, aggregate_forecasts
from app.territory.definitions import ALL_ZONES, ZoneDefinition

logger = logging.getLogger(__name__)

# In-memory cache for latest data (avoids DB reads for API responses)
_current_cache: dict[str, WeatherConditions] = {}
_forecast_cache: dict[str, ZoneForecast] = {}
_alert_cache: dict[str, list[AlertSchema]] = {}


async def _fetch_zone_current(zone: ZoneDefinition) -> WeatherConditions:
    """Fetch and aggregate current conditions for a zone from all sources."""
    results = await asyncio.gather(
        nws_client.fetch_current(zone),
        owm_client.fetch_current(zone),
        visual_crossing_client.fetch_current(zone),
        return_exceptions=True,
    )
    observations = [r for r in results if isinstance(r, WeatherConditions)]
    return aggregate_current(observations, zone.zone_id)


async def _fetch_zone_forecast(zone: ZoneDefinition) -> ZoneForecast:
    """Fetch and aggregate forecasts for a zone from all sources."""
    results = await asyncio.gather(
        nws_client.fetch_forecast(zone),
        owm_client.fetch_forecast(zone),
        visual_crossing_client.fetch_forecast(zone),
        return_exceptions=True,
    )
    forecasts = [r for r in results if isinstance(r, ZoneForecast)]
    return aggregate_forecasts(forecasts, zone.zone_id)


async def ingest_all_zones():
    """Main ingest task: fetch weather for all zones and store results."""
    logger.info("Starting weather ingest for %d zones", len(ALL_ZONES))

    for zone in ALL_ZONES:
        try:
            current, forecast, alerts = await asyncio.gather(
                _fetch_zone_current(zone),
                _fetch_zone_forecast(zone),
                nws_client.fetch_alerts(zone),
            )

            _current_cache[zone.zone_id] = current
            _forecast_cache[zone.zone_id] = forecast
            _alert_cache[zone.zone_id] = alerts

            _persist(zone.zone_id, current, forecast, alerts)
            logger.info("Ingested weather for zone %s", zone.zone_id)

        except Exception as e:
            logger.error("Failed to ingest zone %s: %s", zone.zone_id, e)

    logger.info("Weather ingest complete")


def _persist(
    zone_id: str,
    current: WeatherConditions,
    forecast: ZoneForecast,
    alerts: list[AlertSchema],
):
    """Persist weather data to database."""
    db: Session = SessionLocal()
    try:
        if current.observed_at:
            obs = WeatherObservation(
                zone_id=zone_id,
                source=current.source,
                observed_at=current.observed_at,
                temperature_f=current.temperature_f,
                feels_like_f=current.feels_like_f,
                humidity_pct=current.humidity_pct,
                wind_speed_mph=current.wind_speed_mph,
                wind_gust_mph=current.wind_gust_mph,
                wind_direction_deg=current.wind_direction_deg,
                precip_rate_in_hr=current.precip_rate_in_hr,
                precip_probability_pct=current.precip_probability_pct,
                snow_rate_in_hr=current.snow_rate_in_hr,
                ice_accum_in=current.ice_accum_in,
                visibility_mi=current.visibility_mi,
                cloud_cover_pct=current.cloud_cover_pct,
                pressure_mb=current.pressure_mb,
                lightning_probability_pct=current.lightning_probability_pct,
                condition_text=current.condition_text,
            )
            db.add(obs)

        now = datetime.now(timezone.utc)
        for pt in forecast.points:
            fc = WeatherForecast(
                zone_id=zone_id,
                source=forecast.source,
                forecast_for=pt.forecast_for,
                fetched_at=now,
                temperature_f=pt.temperature_f,
                wind_speed_mph=pt.wind_speed_mph,
                wind_gust_mph=pt.wind_gust_mph,
                precip_probability_pct=pt.precip_probability_pct,
                precip_amount_in=pt.precip_amount_in,
                snow_amount_in=pt.snow_amount_in,
                ice_accum_in=pt.ice_accum_in,
                lightning_probability_pct=pt.lightning_probability_pct,
                condition_text=pt.condition_text,
            )
            db.add(fc)

        for a in alerts:
            existing = db.query(WeatherAlert).filter_by(alert_id=a.alert_id).first()
            if not existing:
                alert_obj = WeatherAlert(
                    zone_id=zone_id,
                    alert_id=a.alert_id,
                    event=a.event,
                    severity=a.severity,
                    urgency=a.urgency,
                    certainty=a.certainty,
                    headline=a.headline,
                    description=a.description,
                    instruction=a.instruction,
                    onset=a.onset,
                    expires=a.expires,
                )
                db.add(alert_obj)

        db.commit()
    except Exception as e:
        db.rollback()
        logger.error("Failed to persist weather for %s: %s", zone_id, e)
    finally:
        db.close()


def get_cached_current(zone_id: str) -> WeatherConditions | None:
    return _current_cache.get(zone_id)


def get_cached_forecast(zone_id: str) -> ZoneForecast | None:
    return _forecast_cache.get(zone_id)


def get_cached_alerts(zone_id: str) -> list[AlertSchema]:
    return _alert_cache.get(zone_id, [])


def get_all_cached_alerts() -> list[AlertSchema]:
    alerts = []
    for zone_alerts in _alert_cache.values():
        alerts.extend(zone_alerts)
    return alerts
