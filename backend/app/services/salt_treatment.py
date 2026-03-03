"""Salt/plow treatment data orchestrator.

Fetches from PlowNYC, DSNY Salt, and 511NY in parallel, computes a per-zone
treatment score (0-1), and caches for use by the melt risk model.

Pattern follows outage_ingest.py: module-level cache, async ingest, getter.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from app.services import plownyc_client, dsny_salt_client, ny511_winter_client

logger = logging.getLogger(__name__)


@dataclass
class ZoneTreatmentStatus:
    zone_id: str
    treatment_score: float | None  # 0.0-1.0, None = no data
    plow_coverage: float | None  # 0.0-1.0
    salt_active: bool | None
    salt_recent: bool | None  # dispensed within 12h but not active
    road_treatment_coverage: float | None  # 0.0-1.0
    updated_at: datetime


# In-memory cache for latest treatment status per zone
_treatment_cache: dict[str, ZoneTreatmentStatus] = {}


def _compute_treatment_score(
    plow_coverage: float | None,
    salt_active: bool | None,
    salt_recent: bool | None,
    road_coverage: float | None,
) -> float | None:
    """Compute weighted treatment score from available sources.

    Weights: plow 0.4, salt 0.4, road conditions 0.2.
    Only available sources contribute; weights re-normalized dynamically.
    Returns None when no sources have data.
    """
    components: list[tuple[float, float]] = []  # (value, weight)

    if plow_coverage is not None:
        components.append((plow_coverage, 0.4))

    if salt_active is not None:
        if salt_active:
            salt_signal = 1.0
        elif salt_recent:
            salt_signal = 0.5
        else:
            salt_signal = 0.0
        components.append((salt_signal, 0.4))

    if road_coverage is not None:
        components.append((road_coverage, 0.2))

    if not components:
        return None

    total_weight = sum(w for _, w in components)
    score = sum(v * w for v, w in components) / total_weight
    return round(min(1.0, max(0.0, score)), 3)


async def ingest_treatment_data():
    """Fetch all treatment sources in parallel and update cache."""
    logger.info("Starting treatment data ingest")
    now = datetime.now(timezone.utc)

    results = await asyncio.gather(
        plownyc_client.fetch_plow_activity(),
        dsny_salt_client.fetch_salt_usage(),
        ny511_winter_client.fetch_road_conditions(),
        return_exceptions=True,
    )

    plow_data = results[0] if isinstance(results[0], list) else []
    salt_data = results[1] if isinstance(results[1], list) else []
    road_data = results[2] if isinstance(results[2], list) else []

    if isinstance(results[0], Exception):
        logger.warning("PlowNYC source failed: %s", results[0])
    if isinstance(results[1], Exception):
        logger.warning("DSNY Salt source failed: %s", results[1])
    if isinstance(results[2], Exception):
        logger.warning("511NY source failed: %s", results[2])

    # Index by zone_id
    plow_by_zone = {p.zone_id: p for p in plow_data}
    salt_by_zone = {s.zone_id: s for s in salt_data}
    road_by_zone = {r.zone_id: r for r in road_data}

    # All zones that have any data
    all_zone_ids = set(plow_by_zone) | set(salt_by_zone) | set(road_by_zone)

    for zone_id in all_zone_ids:
        plow = plow_by_zone.get(zone_id)
        salt = salt_by_zone.get(zone_id)
        road = road_by_zone.get(zone_id)

        plow_cov = plow.coverage_pct if plow else None
        salt_act = salt.dispensing_active if salt else None
        # salt_recent: we have data but not actively dispensing
        salt_rec = (not salt.dispensing_active and salt.tons_dispensed > 0) if salt else None
        road_cov = road.treatment_coverage if road else None

        score = _compute_treatment_score(plow_cov, salt_act, salt_rec, road_cov)

        _treatment_cache[zone_id] = ZoneTreatmentStatus(
            zone_id=zone_id,
            treatment_score=score,
            plow_coverage=plow_cov,
            salt_active=salt_act,
            salt_recent=salt_rec,
            road_treatment_coverage=road_cov,
            updated_at=now,
        )

    logger.info("Treatment ingest complete: %d zones updated", len(all_zone_ids))


def get_treatment_score(zone_id: str) -> float | None:
    """Get cached treatment score for a zone. Returns None if no data."""
    status = _treatment_cache.get(zone_id)
    if status is None:
        return None
    return status.treatment_score


def get_treatment_status(zone_id: str) -> ZoneTreatmentStatus | None:
    """Get full cached treatment status for a zone."""
    return _treatment_cache.get(zone_id)
