"""Modèles SQLAlchemy uniques de la serre (schéma 2)."""

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, Float, Boolean
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass


class SimulationRun(Base):
    __tablename__ = "simulation_runs"
    run_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    first_received_at: Mapped[str] = mapped_column(String(27))


class GreenhouseReading(Base):
    __tablename__ = "sensor_readings"
    __table_args__ = (
        CheckConstraint("schema_version = 2"),
        CheckConstraint("simulated_tick BETWEEN 0 AND 24"),
        CheckConstraint("state_revision >= simulated_tick"),
        CheckConstraint("soil_moisture_sim_pct BETWEEN 0 AND 100"),
        CheckConstraint("air_humidity_pct BETWEEN 0 AND 100"),
        CheckConstraint("plant_id IN ('basilic_01', 'thym_01', 'romarin_01')"),
        Index("ix_readings_run_plant_revision", "run_id", "plant_id", "state_revision", "emitted_at"),
    )
    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("simulation_runs.run_id"))
    schema_version: Mapped[int] = mapped_column(Integer)
    plant_id: Mapped[str] = mapped_column(String(50))
    observed_at: Mapped[str] = mapped_column(String(27))
    simulated_at: Mapped[str] = mapped_column(String(27))
    emitted_at: Mapped[str] = mapped_column(String(27))
    received_at: Mapped[str] = mapped_column(String(27))
    simulated_tick: Mapped[int] = mapped_column(Integer)
    state_revision: Mapped[int] = mapped_column(Integer)
    paused: Mapped[bool] = mapped_column(Boolean(create_constraint=True))
    completed: Mapped[bool] = mapped_column(Boolean(create_constraint=True))
    air_temperature_c: Mapped[float] = mapped_column(Float)
    air_humidity_pct: Mapped[float] = mapped_column(Float)
    soil_moisture_sim_pct: Mapped[float] = mapped_column(Float)
    pump_active: Mapped[bool] = mapped_column(Boolean(create_constraint=True))
    provenance: Mapped[str] = mapped_column(String(80))
    measurement_origin: Mapped[str] = mapped_column(String(30))


class SimulationEventRow(Base):
    __tablename__ = "simulation_events"
    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("simulation_runs.run_id"))
    control_id: Mapped[str | None] = mapped_column(String(36), index=True)
    received_at: Mapped[str] = mapped_column(String(27))
    payload: Mapped[str] = mapped_column(String)


