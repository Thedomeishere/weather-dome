from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {},
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    import app.models.weather  # noqa: F401
    import app.models.impact  # noqa: F401
    import app.models.outage  # noqa: F401
    Base.metadata.create_all(bind=engine)

    # Safe migration: add missing columns to existing SQLite tables
    if "sqlite" in settings.database_url:
        from sqlalchemy import text
        with engine.connect() as conn:
            migrations = [
                ("weather_observations", "snow_depth_in", "FLOAT"),
                ("weather_forecasts", "snow_depth_in", "FLOAT"),
                ("impact_assessments", "job_count_estimate", "JSON"),
            ]
            for table, column, col_type in migrations:
                try:
                    conn.execute(text(
                        f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"
                    ))
                    conn.commit()
                except Exception:
                    conn.rollback()  # column already exists
