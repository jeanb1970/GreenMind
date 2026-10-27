"""Persistance atomique et lecture des mesures de la serre."""

from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session
from uuid import UUID
from greenmind.db.models import SimulationRun, GreenhouseReading, SimulationEventRow
from greenmind.schemas import TelemetryV2, SimulationEvent

def _utc_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def save_message(engine, message: TelemetryV2 | SimulationEvent) -> bool:
    received_at = _utc_text(datetime.now(timezone.utc))
    if isinstance(message, TelemetryV2):
        model = GreenhouseReading
        values = message.model_dump()
        for key in ("event_id", "run_id"):
            values[key] = str(values[key])
        for key in ("observed_at", "simulated_at", "emitted_at"):
            values[key] = _utc_text(values[key])
        values["received_at"] = received_at
    else:
        model = SimulationEventRow
        values = dict(event_id=str(message.event_id), run_id=str(message.run_id),
                      control_id=str(message.control_id) if message.control_id else None,
                      received_at=received_at, payload=message.model_dump_json())
    with Session(engine) as session, session.begin():
        session.execute(insert(SimulationRun).values(
            run_id=str(message.run_id), first_received_at=received_at,
        ).on_conflict_do_nothing(index_elements=["run_id"]))
        inserted = session.scalar(insert(model).values(**values)
                                  .on_conflict_do_nothing(index_elements=["event_id"])
                                  .returning(model.event_id))
    return inserted is not None


def latest_reading(engine, run_id: str | UUID, plant_id: str) -> GreenhouseReading | None:
    """Une mesure tardive d'une ancienne révision ne remplace jamais l'état actuel."""
    with Session(engine) as session:
        return session.scalar(select(GreenhouseReading).where(
            GreenhouseReading.run_id == str(run_id), GreenhouseReading.plant_id == plant_id,
        ).order_by(GreenhouseReading.state_revision.desc(),
                   GreenhouseReading.emitted_at.desc(), GreenhouseReading.event_id.desc()).limit(1))
