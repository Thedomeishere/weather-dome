"""DSNY salt usage client.

Fetches salt dispensing data from NYC Open Data (Socrata SODA API).
No authentication required; optional app token raises rate limit.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# DSNY borough field → zone_id
_BOROUGH_TO_ZONE: dict[str, str] = {
    "Manhattan": "CONED-MAN",
    "Bronx": "CONED-BRX",
    "Brooklyn": "CONED-BKN",
    "Queens": "CONED-QNS",
    "Staten Island": "CONED-SI",
}


@dataclass
class SaltUsage:
    zone_id: str
    tons_dispensed: float
    dispensing_active: bool  # True if dispensed within last 3 hours
    last_dispensed_at: datetime | None


async def fetch_salt_usage(hours: int = 12) -> list[SaltUsage]:
    """Fetch recent salt dispensing data aggregated by borough."""
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime(
            "%Y-%m-%dT%H:%M:%S"
        )
        headers = {}
        if settings.nyc_opendata_app_token:
            headers["X-App-Token"] = settings.nyc_opendata_app_token

        params = {
            "$select": "borough, sum(tons) as total_tons, max(date) as latest",
            "$where": f"date > '{cutoff}'",
            "$group": "borough",
        }

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                settings.dsny_salt_api_url, params=params, headers=headers,
            )
            resp.raise_for_status()
            rows = resp.json()

        now = datetime.now(timezone.utc)
        results: list[SaltUsage] = []
        for row in rows:
            borough = row.get("borough", "")
            zone_id = _BOROUGH_TO_ZONE.get(borough)
            if not zone_id:
                continue
            tons = float(row.get("total_tons", 0))
            latest = _parse_datetime(row.get("latest"))
            active = False
            if latest is not None:
                active = (now - latest).total_seconds() < 3 * 3600  # within 3 hours
            results.append(SaltUsage(
                zone_id=zone_id,
                tons_dispensed=tons,
                dispensing_active=active,
                last_dispensed_at=latest,
            ))

        logger.info("DSNY Salt: fetched usage for %d boroughs", len(results))
        return results

    except Exception as e:
        logger.warning("DSNY Salt fetch failed: %s", e)
        return []


def _parse_datetime(val) -> datetime | None:
    if val is None:
        return None
    try:
        return datetime.fromisoformat(str(val).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
