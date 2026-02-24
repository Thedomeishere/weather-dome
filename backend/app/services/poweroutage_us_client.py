"""PowerOutage.us client.

Fetches utility-wide customer outage count for ConEd (utility ID 419).
Supports two modes:
  - Scrape (default, no key): parse HTML from public utility page
  - API (if POWEROUTAGE_US_API_KEY set): JSON API call
Distributes total across ConEd zones proportionally by peak_load_share.
"""

import logging
import re
from datetime import datetime, timezone

import httpx

from app.config import settings
from app.schemas.outage import OutageIncident
from app.territory.definitions import CONED_ZONES

logger = logging.getLogger(__name__)

_SCRAPE_URL = "https://poweroutage.us/area/utility/419"
_OUTAGE_PATTERN = re.compile(r"([\d,]+)\s*homes and businesses are without power")


async def fetch_incidents() -> list[OutageIncident]:
    """Fetch outage count from PowerOutage.us and distribute across ConEd zones."""
    try:
        if settings.poweroutage_us_api_key and settings.poweroutage_us_api_url:
            total_customers = await _fetch_api()
        else:
            total_customers = await _fetch_scrape()

        if total_customers is None or total_customers == 0:
            logger.info("PowerOutage.us: no outages reported or fetch returned 0")
            return []

        return _distribute(total_customers)

    except Exception as e:
        logger.warning("PowerOutage.us fetch failed: %s", e)
        return []


async def _fetch_api() -> int | None:
    """Fetch via API with key."""
    async with httpx.AsyncClient(timeout=15) as client:
        headers = {"Authorization": f"Bearer {settings.poweroutage_us_api_key}"}
        resp = await client.get(settings.poweroutage_us_api_url, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        # Expected: {"CustomersOut": 1234, ...} or similar
        if isinstance(data, dict):
            return data.get("CustomersOut") or data.get("customers_out", 0)
        return None


async def _fetch_scrape() -> int | None:
    """Scrape public utility page for outage count."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            _SCRAPE_URL,
            headers={"User-Agent": "WeatherDome/1.0 (weather monitoring)"},
        )
        resp.raise_for_status()
        match = _OUTAGE_PATTERN.search(resp.text)
        if match:
            return int(match.group(1).replace(",", ""))
        logger.debug("PowerOutage.us: outage pattern not found in HTML")
        return None


def _distribute(total_customers: int) -> list[OutageIncident]:
    """Distribute utility-wide customer count across ConEd zones by peak_load_share."""
    now_ts = int(datetime.now(timezone.utc).timestamp())
    incidents = []
    for zone in CONED_ZONES:
        share = zone.peak_load_share
        zone_customers = round(total_customers * share)

        incidents.append(OutageIncident(
            incident_id=f"pous-{zone.zone_id}-{now_ts}",
            source="poweroutage_us",
            status="ongoing",
            started_at=datetime.now(timezone.utc),
            region=zone.name,
            latitude=zone.latitude,
            longitude=zone.longitude,
            customers_affected=zone_customers,
        ))

    logger.info("PowerOutage.us: fetched %d customers affected", total_customers)
    return incidents
