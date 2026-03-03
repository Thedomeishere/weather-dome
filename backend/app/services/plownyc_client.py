"""PlowNYC plow activity client.

Fetches street-segment plow/salt activity from NYC Open Data (Socrata SODA API).
No authentication required; optional app token raises rate limit.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# PlowNYC borough field → zone_id
_BOROUGH_TO_ZONE: dict[str, str] = {
    "Manhattan": "CONED-MAN",
    "Bronx": "CONED-BRX",
    "Brooklyn": "CONED-BKN",
    "Queens": "CONED-QNS",
    "Staten Island": "CONED-SI",
}


@dataclass
class PlowActivity:
    zone_id: str
    segments_serviced: int
    total_segments: int
    most_recent_service: datetime | None
    coverage_pct: float  # 0.0 - 1.0


async def fetch_plow_activity(hours: int = 6) -> list[PlowActivity]:
    """Fetch recent plow activity aggregated by borough from PlowNYC."""
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime(
            "%Y-%m-%dT%H:%M:%S"
        )
        headers = {}
        if settings.nyc_opendata_app_token:
            headers["X-App-Token"] = settings.nyc_opendata_app_token

        async with httpx.AsyncClient(timeout=15) as client:
            # Get serviced counts per borough since cutoff
            serviced_params = {
                "$select": "borough, count(*) as serviced_count, max(statusdate) as latest",
                "$where": f"statusdate > '{cutoff}' AND sectionsserviced > 0",
                "$group": "borough",
            }
            resp = await client.get(
                settings.plownyc_api_url, params=serviced_params, headers=headers,
            )
            resp.raise_for_status()
            serviced_rows = resp.json()

            # Get total segments per borough
            total_params = {
                "$select": "borough, count(*) as total_count",
                "$group": "borough",
            }
            resp2 = await client.get(
                settings.plownyc_api_url, params=total_params, headers=headers,
            )
            resp2.raise_for_status()
            total_rows = resp2.json()

        totals: dict[str, int] = {}
        for row in total_rows:
            borough = row.get("borough", "")
            totals[borough] = int(row.get("total_count", 0))

        results: list[PlowActivity] = []
        for row in serviced_rows:
            borough = row.get("borough", "")
            zone_id = _BOROUGH_TO_ZONE.get(borough)
            if not zone_id:
                continue
            serviced = int(row.get("serviced_count", 0))
            total = totals.get(borough, serviced)
            coverage = serviced / total if total > 0 else 0.0
            latest = _parse_datetime(row.get("latest"))
            results.append(PlowActivity(
                zone_id=zone_id,
                segments_serviced=serviced,
                total_segments=total,
                most_recent_service=latest,
                coverage_pct=min(1.0, coverage),
            ))

        logger.info("PlowNYC: fetched activity for %d boroughs", len(results))
        return results

    except Exception as e:
        logger.warning("PlowNYC fetch failed: %s", e)
        return []


def _parse_datetime(val) -> datetime | None:
    if val is None:
        return None
    try:
        return datetime.fromisoformat(str(val).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
