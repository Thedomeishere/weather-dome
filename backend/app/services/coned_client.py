"""ConEd Outage Map client.

Fetches territory-wide outage totals from outagemap.coned.com and distributes
them proportionally across ConEd zones using peak_load_share.
No authentication required. Updates every 15-30 minutes on the source side.
"""

import logging
from datetime import datetime, timezone

import httpx

from app.config import settings
from app.schemas.outage import OutageIncident
from app.territory.definitions import CONED_ZONES

logger = logging.getLogger(__name__)


async def fetch_incidents() -> list[OutageIncident]:
    """Fetch ConEd outage map data and distribute across zones."""
    base_url = settings.coned_outage_map_url
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            # Step 1: get latest data directory from metadata
            meta_resp = await client.get(f"{base_url}/metadata.json")
            meta_resp.raise_for_status()
            directory = meta_resp.json()["directory"]

            # Step 2: fetch actual outage data
            data_resp = await client.get(f"{base_url}/{directory}/data.json")
            data_resp.raise_for_status()
            data = data_resp.json()

        return _parse_summary(data)

    except Exception as e:
        logger.warning("ConEd outage map fetch failed: %s", e)
        return []


def _parse_summary(data: dict) -> list[OutageIncident]:
    """Parse summaryFileData and distribute totals across ConEd zones."""
    summary = data.get("summaryFileData", {})
    total_outages = summary.get("total_outages", 0)

    # total_cust_a can be a dict with "val" key or a plain int
    cust_a = summary.get("total_cust_a", 0)
    if isinstance(cust_a, dict):
        total_customers = cust_a.get("val", 0)
    else:
        total_customers = int(cust_a)

    date_generated = _parse_datetime(summary.get("date_generated"))

    incidents = []
    for zone in CONED_ZONES:
        share = zone.peak_load_share
        zone_customers = round(total_customers * share)
        zone_outages = max(1, round(total_outages * share)) if total_outages > 0 else 0

        incidents.append(OutageIncident(
            incident_id=f"coned-{zone.zone_id}-{int(datetime.now(timezone.utc).timestamp())}",
            source="coned",
            status="ongoing" if zone_outages > 0 else "none",
            started_at=date_generated,
            region=zone.name,
            latitude=zone.latitude,
            longitude=zone.longitude,
            customers_affected=zone_customers,
        ))

    logger.info(
        "ConEd map: fetched %d total outages, %d customers affected",
        total_outages, total_customers,
    )
    return incidents


def _parse_datetime(val) -> datetime | None:
    if val is None:
        return None
    try:
        return datetime.fromisoformat(str(val).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
