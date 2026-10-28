"""Frontière réseau v2 : topic, schéma et persistance validés ensemble."""

from greenmind.db.readings import save_message
from greenmind.schemas import TelemetryV2, SimulationEvent, WateringEvent, parse_v2


def ingest_telemetry(engine, topic: str, payload: str | bytes, *, retained: bool = False) -> bool:
    if retained:
        raise ValueError("Un message MQTT retained est interdit.")
    if topic == "greenmind/v2/simulation/events":
        message = parse_v2(SimulationEvent, payload)
    elif topic.endswith('/events'):
        message = parse_v2(WateringEvent, payload)
        if topic != f"greenmind/v2/plants/{message.plant_id}/events":
            raise ValueError("Topic d'acquittement incohérent avec le bac ciblé.")
    else:
        message = parse_v2(TelemetryV2, payload)
        if topic != f"greenmind/v2/plants/{message.plant_id}/telemetry":
            raise ValueError("Topic de télémétrie v2 incohérent avec la plante ou la version.")
    return save_message(engine, message)
