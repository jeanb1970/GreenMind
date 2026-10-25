"""Modèles SQLAlchemy pour la persistance GreenMind."""

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Float,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base commune aux tables GreenMind."""


class SensorReading(Base):
    """Une mesure validée reçue par MQTT."""

    __tablename__ = "sensor_readings"

    __table_args__ = (
        CheckConstraint(
            "schema_version = 1",
            name="ck_readings_schema_version",
        ),
        CheckConstraint(
            "simulated_tick >= 1",
            name="ck_readings_positive_tick",
        ),
        CheckConstraint(
            "air_humidity_pct BETWEEN 0 AND 100",
            name="ck_readings_air_humidity",
        ),
        CheckConstraint(
            "soil_moisture_sim_pct BETWEEN 0 AND 100",
            name="ck_readings_soil_moisture",
        ),
        Index(
            "ix_readings_plant_emitted",
            "plant_id",
            "emitted_at",
        ),
    )

    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    plant_id: Mapped[str] = mapped_column(String(50), nullable=False)

    # Format de stockage imposé par la future fonction d'insertion :
    # ISO 8601 en UTC, avec six chiffres de microsecondes et suffixe Z.
    # Exemple : 2026-10-25T15:27:31.409452Z
    observed_at: Mapped[str] = mapped_column(String(27), nullable=False)
    emitted_at: Mapped[str] = mapped_column(String(27), nullable=False)

    simulated_tick: Mapped[int] = mapped_column(Integer, nullable=False)
    air_temperature_c: Mapped[float] = mapped_column(Float, nullable=False)
    air_humidity_pct: Mapped[float] = mapped_column(Float, nullable=False)
    soil_moisture_sim_pct: Mapped[float] = mapped_column(
        Float, nullable=False
    )
    pump_active: Mapped[bool] = mapped_column(
        Boolean(create_constraint=True), nullable=False
    )
    provenance: Mapped[str] = mapped_column(String(80), nullable=False)