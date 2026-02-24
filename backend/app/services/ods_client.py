"""ODS (Open Data Sources) outage incident client.

Fetches power outage incidents from the free ODS API.
"""

import logging
from datetime import datetime, timezone

import httpx

from app.config import settings
from app.schemas.outage import OutageIncident

logger = logging.getLogger(__name__)


async def fetch_incidents() -> list[OutageIncident]:
    """Fetch ongoing power outage incidents from ODS API."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(settings.ods_api_url)
            resp.raise_for_status()
            data = resp.json()

            incidents = []
            items = data if isinstance(data, list) else data.get("incidents", data.get("data", []))

            for item in items:
                # Filter to power incidents that are ongoing
                kind = item.get("kind", "").lower()
                status = item.get("status", "").lower()
                if kind and kind != "power":
                    continue
                if status and status not in ("ongoing", "active", ""):
                    continue

                incident = OutageIncident(
                    incident_id=str(item.get("id", item.get("incident_id", ""))),
                    source="ods",
                    status=status or "ongoing",
                    started_at=_parse_datetime(item.get("started_at", item.get("created_at"))),
                    region=item.get("region", item.get("location", "")),
                    latitude=_safe_float(item.get("latitude", item.get("lat"))),
                    longitude=_safe_float(item.get("longitude", item.get("lon", item.get("lng")))),
                    customers_affected=int(item.get("customers_affected", item.get("customers", 0)) or 0),
                    cause=item.get("cause"),
                )
                incidents.append(incident)

            logger.info("ODS: fetched %d power incidents", len(incidents))
            return incidents

    except Exception as e:
        logger.warning("ODS fetch failed: %s", e)
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
