from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Integer, String, Text
from sqlalchemy.sql import func

from app.database import Base


class WeatherObservation(Base):
    __tablename__ = "weather_observations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    zone_id = Column(String(10), nullable=False, index=True)
    source = Column(String(30), nullable=False)  # nws, owm, visual_crossing, aggregated
    observed_at = Column(DateTime, nullable=False)
    temperature_f = Column(Float)
    feels_like_f = Column(Float)
    humidity_pct = Column(Float)
    wind_speed_mph = Column(Float)
    wind_gust_mph = Column(Float)
    wind_direction_deg = Column(Float)
    precip_rate_in_hr = Column(Float)
    precip_probability_pct = Column(Float)
    snow_rate_in_hr = Column(Float)
    snow_depth_in = Column(Float)
    ice_accum_in = Column(Float)
    visibility_mi = Column(Float)
    cloud_cover_pct = Column(Float)
    pressure_mb = Column(Float)
    lightning_probability_pct = Column(Float)
    condition_text = Column(String(100))
    raw_json = Column(Text)
    created_at = Column(DateTime, server_default=func.now())


class WeatherForecast(Base):
    __tablename__ = "weather_forecasts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    zone_id = Column(String(10), nullable=False, index=True)
    source = Column(String(30), nullable=False)
    forecast_for = Column(DateTime, nullable=False)
    fetched_at = Column(DateTime, nullable=False)
    temperature_f = Column(Float)
    feels_like_f = Column(Float)
    humidity_pct = Column(Float)
    wind_speed_mph = Column(Float)
    wind_gust_mph = Column(Float)
    wind_direction_deg = Column(Float)
    precip_probability_pct = Column(Float)
    precip_amount_in = Column(Float)
    snow_amount_in = Column(Float)
    snow_depth_in = Column(Float)
    ice_accum_in = Column(Float)
    cloud_cover_pct = Column(Float)
    lightning_probability_pct = Column(Float)
    condition_text = Column(String(100))
    raw_json = Column(Text)
    created_at = Column(DateTime, server_default=func.now())


class WeatherAlert(Base):
    __tablename__ = "weather_alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    zone_id = Column(String(10), nullable=False, index=True)
    alert_id = Column(String(200), nullable=False, unique=True)
    event = Column(String(100), nullable=False)
    severity = Column(String(20), nullable=False)  # Minor, Moderate, Severe, Extreme
    urgency = Column(String(20))
    certainty = Column(String(20))
    headline = Column(String(500))
    description = Column(Text)
    instruction = Column(Text)
    onset = Column(DateTime)
    expires = Column(DateTime)
    source = Column(String(30), default="nws")
    created_at = Column(DateTime, server_default=func.now())
