from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    # Database
    database_url: str = Field(default="sqlite:///./weather_dome.db")

    # API Keys
    owm_api_key: str = Field(default="")
    visual_crossing_api_key: str = Field(default="")

    # Scheduler intervals (minutes)
    weather_ingest_interval: int = Field(default=15)
    impact_compute_interval: int = Field(default=30)

    # Dashboard polling interval (seconds) - sent to frontend
    dashboard_poll_interval: int = Field(default=60)

    # Wind thresholds (mph)
    wind_advisory_threshold: float = Field(default=35.0)
    wind_warning_threshold: float = Field(default=58.0)
    wind_extreme_threshold: float = Field(default=74.0)

    # Ice thresholds (inches)
    ice_advisory_threshold: float = Field(default=0.1)
    ice_warning_threshold: float = Field(default=0.25)
    ice_extreme_threshold: float = Field(default=0.5)

    # Temperature thresholds (F)
    heat_advisory_threshold: float = Field(default=95.0)
    cold_advisory_threshold: float = Field(default=10.0)

    # Load capacity (MW)
    coned_peak_capacity_mw: float = Field(default=13400.0)
    or_peak_capacity_mw: float = Field(default=1300.0)

    # NYC Open Data 311 outage complaints API
    nyc311_api_url: str = Field(default="https://data.cityofnewyork.us/resource/erm2-nwe9.json")
    nyc_opendata_app_token: str = Field(default="")  # optional, raises rate limit
    outage_ingest_interval: int = Field(default=10)  # minutes

    # ConEd Outage Map
    coned_outage_map_url: str = Field(default="https://outagemap.coned.com/resources/data/external/interval_generation_data")

    # PowerOutage.us (optional API key; scrapes public page if no key)
    poweroutage_us_api_key: str = Field(default="")
    poweroutage_us_api_url: str = Field(default="")

    # Underground melt risk thresholds
    melt_risk_freezing_point_f: float = Field(default=32.0)
    melt_risk_warm_threshold_f: float = Field(default=40.0)
    melt_risk_rapid_warming_rate_f_per_hr: float = Field(default=3.0)

    # Snow depth override (inches). Set when weather APIs don't report
    # snowDepth (NWS NYC stations return None). Set to 0 to disable.
    # This overrides all automatic snow depth estimation.
    snow_depth_override_in: float = Field(default=0.0)

    # CORS
    cors_origins: str = Field(default="http://localhost:5173,http://localhost:3000,https://weather.domevision.org")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",")]


settings = Settings()
