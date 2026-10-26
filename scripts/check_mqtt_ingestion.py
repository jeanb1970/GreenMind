"""Envoi de messages pour contrôler l'ingestion MQTT réelle.

Prérequis : ingestion démarrée et abonnement confirmé.
Ajoute deux mesures synthétiques si le contrôle réussit.
La confirmation du broker ne constitue pas une preuve d'écriture SQL.
"""

import json
import os
from datetime import datetime, timezone
from uuid import uuid4

from paho.mqtt import publish

from greenmind.schemas import parse_telemetry


TOPIC = "greenmind/v1/plants/basilic_01/telemetry"


def main() -> int:
    """Publie un doublon et un message invalide entre deux mesures valides."""
    try:
        host = os.environ.get("GREENMIND_MQTT_HOST", "127.0.0.1")
        port = int(os.environ.get("GREENMIND_MQTT_PORT", "1883"))

        if not 1 <= port <= 65535:
            raise ValueError("Le port MQTT doit être compris entre 1 et 65535.")

        first = {
            "event_id": str(uuid4()),
            "schema_version": 1,
            "plant_id": "basilic_01",
            "observed_at": "2026-07-10T00:00:00Z",
            "emitted_at": datetime.now(timezone.utc).isoformat(),
            "simulated_tick": 1,
            "air_temperature_c": 25.0,
            "air_humidity_pct": 50.0,
            "soil_moisture_sim_pct": 37.5,
            "pump_active": False,
            "provenance": "synthetic_weather_plus_synthetic_soil",
        }

        invalid = {
            **first,
            "event_id": str(uuid4()),
            "soil_moisture_sim_pct": 150.0,
        }

        second = {
            **first,
            "event_id": str(uuid4()),
            "simulated_tick": 2,
            "soil_moisture_sim_pct": 35.0,
        }

        first_json = json.dumps(first)
        second_json = json.dumps(second)

        # Vérifie les deux témoins avant leur publication.
        parse_telemetry(first_json)
        parse_telemetry(second_json)

        print(f"Première mesure et doublon : {first['event_id']}", flush=True)
        print(f"Message invalide : {invalid['event_id']}", flush=True)
        print(f"Mesure après le rejet : {second['event_id']}", flush=True)

        payloads = [
            first_json,
            first_json,
            json.dumps(invalid),
            second_json,
        ]

        publish.multiple(
            [
                {
                    "topic": TOPIC,
                    "payload": payload,
                    "qos": 1,
                    "retain": False,
                }
                for payload in payloads
            ],
            hostname=host,
            port=port,
            client_id=f"greenmind-check-{uuid4().hex[:8]}",
        )

        print("Les quatre publications ont été confirmées par le broker.")
        print(
            "Vérifier maintenant les journaux d'ingestion et SQLite : "
            "deux insertions, un doublon et un rejet attendus."
        )
        return 0

    except KeyboardInterrupt:
        print("\nContrôle interrompu ; résultat incomplet.")
        return 1
    except Exception as error:
        print(f"ÉCHEC du contrôle MQTT : {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())