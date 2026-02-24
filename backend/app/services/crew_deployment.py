"""Crew deployment recommendation model.

Line/tree/service crews based on predicted outages + vegetation risk.
Mutual aid + pre-staging flags for severe events.
"""

from app.schemas.impact import CrewRecommendation, OutageRisk, VegetationRisk
from app.territory.definitions import ZoneDefinition


def compute(
    zone: ZoneDefinition,
    outage_risk: OutageRisk,
    vegetation_risk: VegetationRisk,
) -> CrewRecommendation:
    estimated_outages = outage_risk.estimated_outages

    line_crews = _line_crew_count(estimated_outages, outage_risk.score)
    tree_crews = _tree_crew_count(vegetation_risk.score, estimated_outages)
    service_crews = _service_crew_count(estimated_outages)
    total = line_crews + tree_crews + service_crews

    mutual_aid = outage_risk.score >= 70 or total > 15
    pre_stage = outage_risk.score >= 50

    notes = []
    if mutual_aid:
        notes.append("Request mutual aid from neighboring utilities")
    if pre_stage:
        notes.append("Pre-stage crews in affected areas")
    if vegetation_risk.score >= 60:
        notes.append("Prioritize tree crew deployment for vegetation hazards")
    if outage_risk.level == "Extreme":
        notes.append("Activate emergency operations center")
    if estimated_outages > 1000:
        notes.append(f"Estimated {estimated_outages} outages - consider public communication")

    return CrewRecommendation(
        zone_id=zone.zone_id,
        territory=zone.territory,
        line_crews=line_crews,
        tree_crews=tree_crews,
        service_crews=service_crews,
        total_crews=total,
        mutual_aid_needed=mutual_aid,
        pre_stage=pre_stage,
        notes=notes,
    )


def _line_crew_count(outages: int, risk_score: float) -> int:
    """Line crews restore main feeders and laterals."""
    if outages < 10:
        return 1
    if outages < 50:
        return 2
    if outages < 200:
        return max(3, outages // 50)
    if outages < 1000:
        return max(5, outages // 100)
    return max(10, outages // 200)


def _tree_crew_count(veg_score: float, outages: int) -> int:
    """Tree crews clear vegetation from lines."""
    base = 0
    if veg_score > 20:
        base = 1
    if veg_score > 40:
        base = 2
    if veg_score > 60:
        base = 4
    if veg_score > 80:
        base = 6

    # Additional tree crews if many outages (likely veg-related)
    if outages > 100:
        base += outages // 200

    return base


def _service_crew_count(outages: int) -> int:
    """Service crews handle individual customer restoral."""
    if outages < 20:
        return 1
    if outages < 100:
        return 2
    if outages < 500:
        return max(3, outages // 100)
    return max(5, outages // 200)
