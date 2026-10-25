"""Enregistrement des mesures validées et dédoublonnage événementiel."""

from datetime import datetime, timezone

from sqlalchemy import Engine
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from greenmind.db.models import SensorReading
from greenmind.schemas import TelemetryMessage


def _utc_text(value: datetime) -> str:
    """Produit une date UTC au format fixe utilisé dans SQLite."""
    return (
        value.astimezone(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def save_reading(engine: Engine, message: TelemetryMessage) -> bool:
    """Enregistre une mesure ; retourne False si son identifiant existe déjà.

    Une erreur SQL est propagée au composant appelant.
    Elle ne doit pas être confondue avec un doublon.
    """
    values = message.model_dump()
    values["event_id"] = str(message.event_id)
    values["observed_at"] = _utc_text(message.observed_at)
    values["emitted_at"] = _utc_text(message.emitted_at)

    statement = (
        insert(SensorReading)
        .values(**values)
        .on_conflict_do_nothing(index_elements=["event_id"])
        .returning(SensorReading.event_id)
    )

    with Session(engine) as session:
        with session.begin():
            inserted_id = session.scalar(statement)

    # Ce retour intervient après la validation de la transaction.
    return inserted_id is not None