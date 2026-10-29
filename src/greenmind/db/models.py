"""Modèles SQLAlchemy uniques de la serre (schéma 3)."""

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, Float, Boolean
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass


class SimulationRun(Base):
    __tablename__ = "simulation_runs"
    simulation: Mapped[str] = mapped_column(String(128), primary_key=True)
    first_received_at: Mapped[str] = mapped_column(String(27))


class GreenhouseReading(Base):
    __tablename__ = "sensor_readings"
    __table_args__ = (
        CheckConstraint("schema_version = 3"),
        CheckConstraint("heure_virtuelle BETWEEN 0 AND 24"),
        CheckConstraint("current_state >= heure_virtuelle"),
        CheckConstraint("soil_moisture_pct BETWEEN 0 AND 100"),
        CheckConstraint("air_humidity_pct BETWEEN 0 AND 100"),
        CheckConstraint("plant_id IN ('basilic', 'thym', 'romarin')"),
        Index("ix_readings_run_plant_revision", "simulation", "plant_id", "current_state", "emitted_at"),
    )
    event_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    simulation: Mapped[str] = mapped_column(ForeignKey("simulation_runs.simulation"))
    schema_version: Mapped[int] = mapped_column(Integer)
    plant_id: Mapped[str] = mapped_column(String(50))
    observed_at: Mapped[str] = mapped_column(String(27))
    simulated_at: Mapped[str] = mapped_column(String(27))
    emitted_at: Mapped[str] = mapped_column(String(27))
    received_at: Mapped[str] = mapped_column(String(27))
    cycle: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    heure_virtuelle: Mapped[int] = mapped_column(Integer)
    current_state: Mapped[int] = mapped_column(Integer)
    paused: Mapped[bool] = mapped_column(Boolean(create_constraint=True))
    day_complete: Mapped[bool] = mapped_column(Boolean(create_constraint=True))
    air_temperature_c: Mapped[float] = mapped_column(Float)
    air_humidity_pct: Mapped[float] = mapped_column(Float)
    soil_moisture_pct: Mapped[float] = mapped_column(Float)
    arroseur_active: Mapped[bool] = mapped_column(Boolean(create_constraint=True))
    provenance: Mapped[str] = mapped_column(String(80))
    measurement_origin: Mapped[str] = mapped_column(String(30))


class SimulationEventRow(Base):
    __tablename__ = "simulation_events"
    event_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    simulation: Mapped[str] = mapped_column(ForeignKey("simulation_runs.simulation"))
    control_id: Mapped[str | None] = mapped_column(String(128), index=True)
    received_at: Mapped[str] = mapped_column(String(27))
    payload: Mapped[str] = mapped_column(String)


class SimulationControlRow(Base):
    """Commande REST persistée avant publication, pour un rejeu exact après reprise."""
    __tablename__ = "simulation_controls"
    control_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    simulation: Mapped[str] = mapped_column(ForeignKey("simulation_runs.simulation"))
    payload: Mapped[str] = mapped_column(String)


class AlertRow(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        CheckConstraint("status IN ('ouverte', 'clôturée')"),
        CheckConstraint("plant_id IN ('basilic', 'thym', 'romarin')"),
        Index("ix_alerts_run_plant_status", "simulation", "plant_id", "status"),
    )
    alert_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    simulation: Mapped[str] = mapped_column(ForeignKey("simulation_runs.simulation"), index=True)
    plant_id: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20))
    opened_at: Mapped[str] = mapped_column(String(27))
    closed_at: Mapped[str | None] = mapped_column(String(27), nullable=True)
    opening_event_id: Mapped[str] = mapped_column(String(128))
    closing_event_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    moist_trigger_pct: Mapped[float] = mapped_column(Float)
    moist_resolved_pct: Mapped[float | None] = mapped_column(Float, nullable=True)


class GreenhouseEventRow(Base):
    __tablename__ = "greenhouse_events"
    __table_args__ = (
        Index("ix_events_run_plant_seq", "simulation", "plant_id", "sequence"),
    )
    sequence: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    simulation: Mapped[str] = mapped_column(ForeignKey("simulation_runs.simulation"), index=True)
    plant_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[str] = mapped_column(String(27))
    simulated_at: Mapped[str | None] = mapped_column(String(27), nullable=True)
    event_type: Mapped[str] = mapped_column(String(50), index=True)
    summary: Mapped[str] = mapped_column(String)
    details: Mapped[str] = mapped_column(String, default="{}")




class WateringProposalRow(Base):
    __tablename__ = 'watering_proposals'
    proposal_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    simulation: Mapped[str] = mapped_column(ForeignKey('simulation_runs.simulation'))
    plant_id: Mapped[str] = mapped_column(String(50))
    current_state: Mapped[int] = mapped_column(Integer)
    expires_at: Mapped[str] = mapped_column(String(27))
    payload: Mapped[str] = mapped_column(String)
    consumed_by_command: Mapped[str | None] = mapped_column(String(128), unique=True)


class WateringCommandRow(Base):
    __tablename__ = 'watering_commands'
    __table_args__ = (
        CheckConstraint("status IN ('en_attente', 'envoyé', 'exécuté', 'refusé', 'TIMED_OUT')"),
        Index('ix_watering_run_plant', 'simulation', 'plant_id'),
    )
    command_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    proposal_id: Mapped[str] = mapped_column(ForeignKey('watering_proposals.proposal_id'), unique=True)
    simulation: Mapped[str] = mapped_column(ForeignKey('simulation_runs.simulation'))
    plant_id: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20))
    expires_at: Mapped[str] = mapped_column(String(27))
    payload: Mapped[str] = mapped_column(String)
    reason: Mapped[str] = mapped_column(String)
    executed_at: Mapped[str | None] = mapped_column(String(27))
    resulting_state: Mapped[int | None] = mapped_column(Integer)


class WateringEventRow(Base):
    __tablename__ = 'watering_events'
    event_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    simulation: Mapped[str] = mapped_column(ForeignKey('simulation_runs.simulation'))
    command_id: Mapped[str] = mapped_column(String(128), index=True)
    received_at: Mapped[str] = mapped_column(String(27))
    payload: Mapped[str] = mapped_column(String)
