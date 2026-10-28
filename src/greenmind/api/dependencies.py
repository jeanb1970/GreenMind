"""Dépendances et injection pour l'API REST FastAPI."""

import os
from pathlib import Path
from uuid import uuid4
from fastapi import HTTPException, status
import paho.mqtt.client as mqtt
from greenmind.db.session import create_database_engine, DEFAULT_DATABASE_PATH
from greenmind.greenhouse_config import GreenhouseConfig, load_greenhouse_config

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config/greenhouse.yaml"

_GLOBAL_ENGINE = None
_GLOBAL_CONFIG = None


def get_db():
    global _GLOBAL_ENGINE
    if _GLOBAL_ENGINE is None:
        _GLOBAL_ENGINE = create_database_engine(Path(
            os.environ.get("GREENMIND_DATABASE_PATH", str(DEFAULT_DATABASE_PATH))
        ))
    return _GLOBAL_ENGINE


def get_config() -> GreenhouseConfig:
    global _GLOBAL_CONFIG
    if _GLOBAL_CONFIG is None:
        _GLOBAL_CONFIG = load_greenhouse_config(DEFAULT_CONFIG_PATH)
    return _GLOBAL_CONFIG


class MqttPublisher:
    """Publication QoS 1 des contrôles et arrosages vers le simulateur."""

    def __init__(self, host: str | None = None, port: int | None = None):
        self.host = host or os.environ.get("GREENMIND_MQTT_HOST", "127.0.0.1").strip()
        self.port = port or int(os.environ.get("GREENMIND_MQTT_PORT", "1883"))

    def publish_control(self, payload_json: str) -> None:
        self._publish("greenmind/v2/simulation/controls", payload_json)

    def publish_watering(self, plant_id: str, payload_json: str) -> None:
        self._publish(f"greenmind/v2/plants/{plant_id}/commands", payload_json)

    def _publish(self, topic: str, payload_json: str) -> None:
        client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"greenmind-api-pub-{uuid4().hex[:8]}",
            clean_session=True,
            protocol=mqtt.MQTTv311,
        )
        try:
            client.connect(self.host, self.port, keepalive=10)
            client.loop_start()
            info = client.publish(
                topic,
                payload_json,
                qos=1,
                retain=False,
            )
            info.wait_for_publish(timeout=3.0)
            if not info.is_published():
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Le broker MQTT n'a pas confirmé la publication de la commande.",
                )
        except (OSError, RuntimeError) as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Impossible de contacter le broker MQTT sur {self.host}:{self.port} : {error}.",
            ) from error
        finally:
            client.loop_stop()
            client.disconnect()


_GLOBAL_PUBLISHER = None


def get_publisher() -> MqttPublisher:
    global _GLOBAL_PUBLISHER
    if _GLOBAL_PUBLISHER is None:
        _GLOBAL_PUBLISHER = MqttPublisher()
    return _GLOBAL_PUBLISHER
