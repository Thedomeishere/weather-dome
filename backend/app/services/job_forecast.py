"""Job count forecast model.

Estimates low/mid/high outage job ranges using weather-driven heuristics.
Replaces crew deployment recommendations with predicted outage workload ranges.
"""

from app.schemas.impact import JobCountEstimate, OutageRisk
from app.territory.definitions import ZoneDefinition


def compute(outage_risk: OutageRisk, zone: ZoneDefinition) -> JobCountEstimate:
    mid = _estimate_jobs(outage_risk.score)
    low_mult, high_mult = _uncertainty_band(outage_risk)
    low = max(0, int(mid * low_mult))
    high = int(mid * high_mult)

    factors = _determine_factors(outage_risk)

    return JobCountEstimate(
        zone_id=zone.zone_id,
        territory=zone.territory,
        outage_risk_score=round(outage_risk.score, 1),
        estimated_jobs_low=low,
        estimated_jobs_mid=mid,
        estimated_jobs_high=high,
        risk_level=outage_risk.level,
        contributing_factors=factors,
    )


def _estimate_jobs(score: float) -> int:
    """Reuse the outage_risk scaling heuristic for mid estimate."""
    if score < 10:
        return 0
    if score < 25:
        return int(score * 2)
    if score < 50:
        return int(score * 10)
    if score < 75:
        return int(score * 40)
    return int(score * 100)


def _uncertainty_band(outage_risk: OutageRisk) -> tuple[float, float]:
    """Return (low_multiplier, high_multiplier) based on weather drivers."""
    factors = outage_risk.contributing_factors

    has_ice = any("Ice" in f and "synergy" not in f for f in factors)
    has_wind = any("Wind" in f and "synergy" not in f for f in factors)
    has_synergy = any("Wind+Ice synergy" in f for f in factors)

    if has_synergy:
        # Wind+Ice synergy: cascading failures likely
        return 0.3, 3.0
    if has_ice:
        # Ice events: ice loading hard to predict
        return 0.3, 2.5
    if has_wind:
        # Wind-only events: moderate predictability
        return 0.5, 1.8

    # Calm/low risk: tight band
    return 0.5, 1.5


def _determine_factors(outage_risk: OutageRisk) -> list[str]:
    """Extract contributing factors from outage risk."""
    return list(outage_risk.contributing_factors)
