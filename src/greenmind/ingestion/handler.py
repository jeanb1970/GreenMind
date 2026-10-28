"""Frontière réseau v3 : topic, schéma et persistance validés ensemble."""

from greenmind.db.readings import save_message
from greenmind.schemas import TelemetryV3, SimulationEvent, WateringEvent, parse_v3


def ingest_telemetry(engine, topic: str, payload: str | bytes, *, retained: bool = False) -> bool:
    if retained:
        raise ValueError("Un message MQTT retained est interdit.")
    if topic == "greenmind/v3/simulation/events":
        message = parse_v3(SimulationEvent, payload)
    elif topic.endswith('/events'):
        message = parse_v3(WateringEvent, payload)
        if topic != f"greenmind/v3/plants/{message.plant_id}/events":
            raise ValueError("Topic d'acquittement incohérent avec le bac ciblé.")
    else:
        message = parse_v3(TelemetryV3, payload)
        if topic != f"greenmind/v3/plants/{message.plant_id}/telemetry":
            raise ValueError("Topic de télémétrie v3 incohérent avec la plante ou la version.")
    return save_message(engine, message)
