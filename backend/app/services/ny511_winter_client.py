"""511NY Winter Road Conditions client.

Fetches winter road condition data from 511NY API.
Requires API key (settings.ny511_api_key); returns empty list if not configured.
"""

import logging
from dataclasses import dataclass

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# County name (lowercase) → zone_id
_COUNTY_TO_ZONE: dict[str, str] = {
    "westchester": "CONED-WST",
    "orange": "OR-ORA",
    "rockland": "OR-ROC",
    "sullivan": "OR-SUL",
    "bergen": "OR-BER",
    "passaic": "OR-BER",
    "sussex": "OR-SSX",
}

# Condition strings indicating active treatment
_TREATED_KEYWORDS = ("chemically treated", "plowed", "salted", "treated", "plowed and salted")

# Condition strings indicating winter conditions present
_WINTER_KEYWORDS = ("snow covered", "ice covered", "slippery", "snow packed", "frost")


@dataclass
class RoadConditionSummary:
    zone_id: str
    total_segments: int
    treated_segments: int
    winter_condition_segments: int
    treatment_coverage: float  # 0.0 - 1.0


async def fetch_road_conditions() -> list[RoadConditionSummary]:
    """Fetch winter road conditions from 511NY API.

    Returns empty list immediately if no API key is configured.
    """
    if not settings.ny511_api_key:
        return []

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                settings.ny511_api_url,
                params={"key": settings.ny511_api_key, "format": "json"},
            )
            resp.raise_for_status()
            data = resp.json()

        # Parse response — structure varies; handle list of road segments
        segments = data if isinstance(data, list) else data.get("WinterRoadConditions", [])

        # Aggregate by zone
        zone_stats: dict[str, dict] = {}
        for seg in segments:
            county = (seg.get("County", "") or seg.get("county", "")).lower().strip()
            zone_id = _COUNTY_TO_ZONE.get(county)
            if not zone_id:
                continue

            if zone_id not in zone_stats:
                zone_stats[zone_id] = {"total": 0, "treated": 0, "winter": 0}

            zone_stats[zone_id]["total"] += 1

            condition = (seg.get("Condition", "") or seg.get("condition", "")).lower()
            if any(kw in condition for kw in _TREATED_KEYWORDS):
                zone_stats[zone_id]["treated"] += 1
            if any(kw in condition for kw in _WINTER_KEYWORDS):
                zone_stats[zone_id]["winter"] += 1

        results: list[RoadConditionSummary] = []
        for zone_id, stats in zone_stats.items():
            total = stats["total"]
            coverage = stats["treated"] / total if total > 0 else 0.0
            results.append(RoadConditionSummary(
                zone_id=zone_id,
                total_segments=total,
                treated_segments=stats["treated"],
                winter_condition_segments=stats["winter"],
                treatment_coverage=min(1.0, coverage),
            ))

        logger.info("511NY: fetched conditions for %d zones", len(results))
        return results

    except Exception as e:
        logger.warning("511NY fetch failed: %s", e)
        return []
