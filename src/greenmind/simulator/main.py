"""Publication des mesures du basilic virtuel sur MQTT."""

import os
from datetime import datetime, timezone
from math import isfinite
from pathlib import Path
from threading import Event
from uuid import uuid4

import paho.mqtt.client as mqtt

from greenmind.config import load_plant_config
from greenmind.domain.simulation import dry_one_tick
from greenmind.schemas import TelemetryMessage
from greenmind.simulator.weather import load_weather


PROJECT_ROOT = Path(__file__).resolve().parents[3]
MQTT_TIMEOUT_S = 5.0


def main() -> int:
    """Exécute une fois le scénario météo et ferme la connexion."""
    client = None
    loop_started = False

    try:
        config = load_plant_config(PROJECT_ROOT / "config/plants.yaml")
        weather = load_weather(
            PROJECT_ROOT / "data/fixtures/weather_sample.csv"
        )

        host = os.environ.get("GREENMIND_MQTT_HOST", "127.0.0.1")

        try:
            port = int(os.environ.get("GREENMIND_MQTT_PORT", "1883"))
            period = float(
                os.environ.get("GREENMIND_PUBLICATION_PERIOD_S", "5")
            )
        except ValueError:
            raise ValueError(
                "Le port MQTT doit être entier et la période numérique."
            ) from None

        if not 1 <= port <= 65535:
            raise ValueError("Le port MQTT doit être compris entre 1 et 65535.")

        if not isfinite(period) or period <= 0:
            raise ValueError("La période doit être un nombre fini positif.")

        topic = f"greenmind/v1/plants/{config.plant_id}/telemetry"
        connection_answered = Event()

        client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"greenmind-simulator-{uuid4().hex[:8]}",
            clean_session=True,
            protocol=mqtt.MQTTv311,
        )
        client.connect_timeout = MQTT_TIMEOUT_S

        def on_connect(client, userdata, flags, reason_code, properties):
            if reason_code.is_failure:
                print(
                    f"Connexion MQTT refusée : {reason_code}",
                    flush=True,
                )
            else:
                print("Connexion MQTT établie.", flush=True)
            connection_answered.set()

        def on_disconnect(
            client, userdata, disconnect_flags, reason_code, properties
        ):
            if reason_code.is_failure:
                print(
                    "Connexion MQTT interrompue. "
                    "La prochaine publication devra être confirmée.",
                    flush=True,
                )

        client.on_connect = on_connect
        client.on_disconnect = on_disconnect

        print(f"Connexion à Mosquitto sur {host}:{port}...", flush=True)
        client.connect(host, port, keepalive=60)

        if client.loop_start() != mqtt.MQTT_ERR_SUCCESS:
            raise RuntimeError("Impossible de démarrer la boucle réseau MQTT.")
        loop_started = True

        if not connection_answered.wait(MQTT_TIMEOUT_S):
            raise RuntimeError(
                "Le broker n'a pas confirmé la connexion dans le délai prévu."
            )

        if not client.is_connected():
            raise RuntimeError("La connexion MQTT n'est pas disponible.")

        moisture = config.initial_soil_moisture_sim_pct

        print(
            f"Début du scénario : {config.scenario}. "
            f"{len(weather)} pas, espacés d'au moins {period:g} secondes.",
            flush=True,
        )
        print(f"Topic de publication : {topic}", flush=True)

        # Cette attente reste interruptible par Ctrl+C.
        pause = Event()

        for tick, reading in enumerate(weather, start=1):
            if not client.is_connected():
                raise RuntimeError(
                    "Publication interrompue : connexion MQTT indisponible."
                )

            moisture = dry_one_tick(
                moisture,
                reading.air_temperature_c,
                reading.air_humidity_pct,
                **config.simulation.model_dump(),
            )

            message = TelemetryMessage(
                event_id=uuid4(),
                schema_version=1,
                plant_id=config.plant_id,
                observed_at=reading.observed_at,
                emitted_at=datetime.now(timezone.utc),
                simulated_tick=tick,
                air_temperature_c=reading.air_temperature_c,
                air_humidity_pct=reading.air_humidity_pct,
                soil_moisture_sim_pct=moisture,
                pump_active=False,
                provenance=reading.provenance,
            )

            publication = client.publish(
                topic,
                payload=message.model_dump_json(),
                qos=1,
                retain=False,
            )

            if publication.rc != mqtt.MQTT_ERR_SUCCESS:
                raise RuntimeError(
                    "La publication MQTT n'a pas pu être prise en charge."
                )

            try:
                publication.wait_for_publish(timeout=MQTT_TIMEOUT_S)
            except (RuntimeError, ValueError) as error:
                raise RuntimeError(
                    "Erreur pendant l'attente de confirmation MQTT."
                ) from error

            if not publication.is_published():
                raise RuntimeError(
                    "Publication non confirmée par le broker dans le délai prévu."
                )

            print(
                f"Pas {tick} | humidité simulée : {moisture:.1f} % | "
                f"réception confirmée par le broker | "
                f"événement : {message.event_id}",
                flush=True,
            )

            if tick < len(weather):
                pause.wait(period)

        print("Scénario terminé : toutes les lignes météo ont été publiées.")
        return 0

    except KeyboardInterrupt:
        print("\nArrêt du simulateur demandé au clavier.")
        return 0
    except (ValueError, RuntimeError) as error:
        print(f"Erreur du simulateur : {error}", flush=True)
        return 1
    except OSError:
        print(
            "Erreur réseau : impossible de communiquer avec Mosquitto. "
            "Vérifier le broker, son adresse et son port.",
            flush=True,
        )
        return 1
    finally:
        if client is not None:
            client.disconnect()
            if loop_started:
                client.loop_stop()


if __name__ == "__main__":
    raise SystemExit(main())