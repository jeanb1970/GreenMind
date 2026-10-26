"""Traitement d'une télémétrie reçue depuis MQTT."""

from sqlalchemy import Engine

from greenmind.db.readings import save_reading
from greenmind.schemas import parse_telemetry


def ingest_telemetry(
    engine: Engine,
    topic: str,
    payload: str | bytes,
) -> bool:
    """Valide et enregistre une télémétrie.

    Retourne True après insertion, False pour un événement déjà présent.

    Une ValueError indique un message ou un topic invalide.
    Les erreurs SQL sont propagées au service appelant.
    """
    message = parse_telemetry(payload)

    expected_topic = (
        f"greenmind/v1/plants/{message.plant_id}/telemetry"
    )
    if topic != expected_topic:
        raise ValueError(
            f"Topic de télémétrie invalide : {topic!r}. "
            f"Topic attendu pour cette plante : {expected_topic!r}."
        )

    return save_reading(engine, message)