from sqlalchemy import Column, DateTime, Float, Integer, String, Text, JSON
from sqlalchemy.sql import func

from app.database import Base


class OutageSnapshot(Base):
    """Append-only historical record: one row per zone per ingest cycle."""
    __tablename__ = "outage_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    zone_id = Column(String(10), nullable=False, index=True)
    source = Column(String(30), nullable=False)  # ods, poweroutage_us
    snapshot_at = Column(DateTime, nullable=False)
    outage_count = Column(Integer, default=0)
    customers_affected = Column(Integer, default=0)
    active_incidents = Column(Integer, default=0)
    raw_json = Column(Text)
    created_at = Column(DateTime, server_default=func.now())


class OutageWeatherCorrelation(Base):
    """Forward-looking: calibrated coefficients once enough data accumulates."""
    __tablename__ = "outage_weather_correlations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    zone_id = Column(String(10), nullable=False, index=True)
    computed_at = Column(DateTime, nullable=False)
    wind_correlation = Column(Float)
    ice_correlation = Column(Float)
    precip_correlation = Column(Float)
    snow_correlation = Column(Float)
    temp_correlation = Column(Float)
    calibrated_coefficients = Column(JSON)  # {"wind": 0.4, "ice": 0.3, ...}
    created_at = Column(DateTime, server_default=func.now())
