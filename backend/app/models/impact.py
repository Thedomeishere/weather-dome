from sqlalchemy import Column, DateTime, Float, Integer, String, Text, JSON
from sqlalchemy.sql import func

from app.database import Base


class ImpactAssessment(Base):
    __tablename__ = "impact_assessments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    zone_id = Column(String(10), nullable=False, index=True)
    territory = Column(String(10), nullable=False, index=True)  # CONED or OR
    assessed_at = Column(DateTime, nullable=False)
    forecast_hour = Column(Integer, default=0)  # 0=current, 1-48 for forecast hours

    # Outage risk
    outage_risk_score = Column(Float)  # 0-100
    outage_risk_level = Column(String(20))  # Low, Moderate, High, Extreme
    estimated_outages = Column(Integer)

    # Vegetation risk
    vegetation_risk_score = Column(Float)
    vegetation_risk_level = Column(String(20))

    # Load forecast
    load_forecast_mw = Column(Float)
    load_pct_capacity = Column(Float)
    load_risk_level = Column(String(20))

    # Equipment stress
    equipment_stress_score = Column(Float)
    equipment_stress_level = Column(String(20))
    transformer_risk = Column(Float)
    line_sag_risk = Column(Float)

    # Job count forecast
    job_count_estimate = Column(JSON)  # {"estimated_jobs_low": n, "estimated_jobs_mid": n, ...}

    # Summary
    overall_risk_level = Column(String(20))
    overall_risk_score = Column(Float)
    summary_text = Column(Text)

    created_at = Column(DateTime, server_default=func.now())
