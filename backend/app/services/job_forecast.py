"""Job count forecast model.

Estimates low/mid/high outage job ranges using weather-driven heuristics.
Melt events (manhole fires, cable failures from snowmelt infiltration)
are a primary driver of underground outage jobs in winter.

Calibrated against real ConEd data:
- Park Slope Feb 2026 melt event: ~2,000 customers, ~273 jobs
- Brooklyn 3-7x more vulnerable than Manhattan (less network redundancy)
- Major winter storms: 1,000-3,000 affected customers in NYC underground
- Manhattan network redundancy: single cable faults rarely cause customer outage
"""

from app.schemas.impact import JobCountEstimate, OutageRisk
from app.territory.definitions import ZoneDefinition

# Manhattan's network design provides N-1 redundancy — single cable faults
# rarely cause customer outages. Other boroughs have radial feeds where a
# single fault = customer outage. Research: BKN sees 3-7x more outage
# customers than MAN during identical melt events.
NETWORK_REDUNDANCY_DISCOUNT: dict[str, float] = {
    "CONED-MAN": 0.5,     # High redundancy — fewer jobs per risk unit
    "CONED-BKN": 1.0,     # Radial feeds, oldest infrastructure
    "CONED-QNS": 1.0,     # Similar to Brooklyn
    "CONED-BRX": 0.9,     # Slightly better than BKN
    "CONED-SI": 0.8,      # Mix of systems
    "CONED-WST": 0.7,     # Suburban, less underground
    "OR-ORA": 0.4,
    "OR-ROC": 0.3,
    "OR-SUL": 0.2,
    "OR-BER": 0.3,
    "OR-SSX": 0.2,
}


def compute(
    outage_risk: OutageRisk,
    zone: ZoneDefinition,
    melt_risk_score: float = 0.0,
) -> JobCountEstimate:
    # Melt events directly cause underground outages — combine scores.
    # Reduced melt coefficient from 0.6→0.4 to prevent over-prediction
    # when melt score is inflated from inferred snow depth.
    combined_score = max(
        outage_risk.score,
        melt_risk_score * 0.4 + outage_risk.score * 0.6,
    )

    # Apply network redundancy discount (Manhattan fewer jobs per risk unit)
    redundancy = NETWORK_REDUNDANCY_DISCOUNT.get(zone.zone_id, 0.5)
    weather_mid = _estimate_jobs(combined_score, redundancy)

    # Baseline job floor: even in calm weather, baseline outages always
    # generate restoration work (~0.3 jobs per baseline outage).
    from app.services.outage_risk import BASELINE_OUTAGES
    baseline_jobs = int(BASELINE_OUTAGES.get(zone.zone_id, 5) * 0.3)
    mid = max(weather_mid, baseline_jobs)

    low_mult, high_mult = _uncertainty_band(outage_risk)

    # Widen uncertainty when melt is a major driver (harder to predict)
    if melt_risk_score > 30:
        low_mult = min(low_mult, 0.4)
        high_mult = max(high_mult, 2.0)

    low = max(0, int(mid * low_mult))
    high = int(mid * high_mult)

    factors = _determine_factors(outage_risk, melt_risk_score)

    return JobCountEstimate(
        zone_id=zone.zone_id,
        territory=zone.territory,
        outage_risk_score=round(combined_score, 1),
        estimated_jobs_low=low,
        estimated_jobs_mid=mid,
        estimated_jobs_high=high,
        risk_level=outage_risk.level,
        contributing_factors=factors,
    )


def _estimate_jobs(score: float, redundancy: float = 1.0) -> int:
    """Estimate mid-range job count from combined risk score.

    Uses a smooth quadratic function instead of step function to avoid
    cliff effects at score boundaries.

    Calibration against real ConEd data:
    - Park Slope Feb 2026 melt event: ~273 jobs at combined_score ~43
      → 0.15 * 43^2 * 1.0 (BKN) = 277 jobs ✓
    - Typical moderate event (score ~30): ~135 BKN, ~67 MAN jobs
    - Extreme event (score 85): ~1083 BKN, ~541 MAN jobs
    """
    if score < 3:
        return 0

    # Smooth quadratic: jobs = 0.15 * score^2 * redundancy
    raw_jobs = 0.15 * score * score
    return max(0, int(raw_jobs * redundancy))


def _uncertainty_band(outage_risk: OutageRisk) -> tuple[float, float]:
    """Return (low_multiplier, high_multiplier) based on weather drivers."""
    factors = outage_risk.contributing_factors

    has_ice = any("Ice" in f and "synergy" not in f for f in factors)
    has_wind = any("Wind" in f and "synergy" not in f for f in factors)
    has_snow = any("Snow" in f and "synergy" not in f for f in factors)
    has_synergy = any("synergy" in f for f in factors)
    has_melt = any("melt" in f.lower() for f in factors)

    if has_synergy:
        # Wind+Ice or Wind+Snow synergy: cascading failures likely
        return 0.3, 3.0
    if has_ice:
        # Ice events: ice loading hard to predict
        return 0.3, 2.5
    if has_melt:
        # Melt events: underground infiltration hard to predict
        return 0.3, 2.5
    if has_snow:
        # Snow events: wet snow loading unpredictable
        return 0.4, 2.0
    if has_wind:
        # Wind-only events: moderate predictability
        return 0.5, 1.8

    # Calm/low risk: tight band
    return 0.5, 1.5


def _determine_factors(outage_risk: OutageRisk, melt_risk_score: float = 0.0) -> list[str]:
    """Extract contributing factors from outage risk and melt."""
    factors = list(outage_risk.contributing_factors)
    if melt_risk_score > 20 and not any("melt" in f.lower() for f in factors):
        factors.append("Underground melt risk")
    return factors
