"""NYC Open Data 311 power outage complaints client.

Fetches power outage complaints from NYC 311 via the SODA API.
No authentication required; optional app token raises rate limit.
"""

import logging
from datetime import datetime, timedelta, timezone

import httpx

from app.config import settings
from app.schemas.outage import OutageIncident

logger = logging.getLogger(__name__)


async def fetch_incidents() -> list[OutageIncident]:
    """Fetch recent power outage complaints from NYC 311 SODA API."""
    try:
        since = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime(
            "%Y-%m-%dT%H:%M:%S"
        )
        params = {
            "$where": f"complaint_type='Power Outage' AND created_date > '{since}'",
            "$select": (
                "unique_key,created_date,descriptor,borough,"
                "incident_address,latitude,longitude,status"
            ),
            "$limit": 5000,
        }
        headers = {}
        if settings.nyc_opendata_app_token:
            headers["X-App-Token"] = settings.nyc_opendata_app_token

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                settings.nyc311_api_url, params=params, headers=headers
            )
            resp.raise_for_status()
            rows = resp.json()

            incidents = []
            for row in rows:
                incident = OutageIncident(
                    incident_id=str(row.get("unique_key", "")),
                    source="nyc311",
                    status=row.get("status", "Open").lower(),
                    started_at=_parse_datetime(row.get("created_date")),
                    region=row.get("borough", ""),
                    latitude=_safe_float(row.get("latitude")),
                    longitude=_safe_float(row.get("longitude")),
                    customers_affected=0,  # 311 complaints don't have this field
                    cause=row.get("descriptor"),
                )
                incidents.append(incident)

            logger.info("NYC 311: fetched %d power outage complaints", len(incidents))
            return incidents

    except Exception as e:
        logger.warning("NYC 311 fetch failed: %s", e)
        return []


def _parse_datetime(val) -> datetime | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    try:
        return datetime.fromisoformat(str(val).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _safe_float(val) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None
