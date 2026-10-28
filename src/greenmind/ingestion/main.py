"""Service de réception MQTT et de persistance des télémétries."""

import json
import logging
import os
import signal
from pathlib import Path
from threading import Event
from time import monotonic
from uuid import uuid4

import paho.mqtt.client as mqtt
from sqlalchemy.exc import SQLAlchemyError

from greenmind.db.session import create_database_engine, DEFAULT_DATABASE_PATH
from greenmind.ingestion.handler import ingest_telemetry


LOGGER = logging.getLogger("greenmind.ingestion")

TELEMETRY_TOPICS = [("greenmind/v2/plants/+/telemetry", 1), ("greenmind/v2/simulation/events", 1),
                    ("greenmind/v2/plants/+/events", 1)]
STARTUP_TIMEOUT_S = 10.0
CONNECTION_TIMEOUT_S = 5.0


def main() -> int:
    """Maintient l'ingestion active jusqu'à un arrêt ou une erreur fatale."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    stop_requested = Event()
    subscribed = Event()
    fatal_error = Event()

    engine = None
    client = None
    loop_started = False
    subscription_mid = None
    previous_handlers = {}

    def fail(message: str) -> None:
        """Signale un échec et demande la fermeture des ressources."""
        LOGGER.error("%s", message)
        fatal_error.set()
        stop_requested.set()

    def request_stop(signum, frame):
        # Le nettoyage est réalisé dans le finally du thread principal.
        stop_requested.set()

    try:
        for signum in (signal.SIGINT, signal.SIGTERM):
            previous_handlers[signum] = signal.signal(
                signum, request_stop
            )

        host = os.environ.get(
            "GREENMIND_MQTT_HOST", "127.0.0.1"
        ).strip()

        if not host:
            raise ValueError("L'adresse du broker MQTT ne peut pas être vide.")

        try:
            port = int(os.environ.get("GREENMIND_MQTT_PORT", "1883"))
        except ValueError:
            raise ValueError("Le port MQTT doit être un entier.") from None

        if not 1 <= port <= 65535:
            raise ValueError("Le port MQTT doit être compris entre 1 et 65535.")

        database_engine = create_database_engine(Path(os.environ.get("GREENMIND_DATABASE_PATH", str(DEFAULT_DATABASE_PATH))))
        engine = database_engine
        LOGGER.info("Base SQLite initialisée.")

        client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"greenmind-ingestion-{uuid4().hex[:8]}",
            clean_session=True,
            protocol=mqtt.MQTTv311,
            manual_ack=True,
        )
        client.connect_timeout = CONNECTION_TIMEOUT_S
        client.reconnect_delay_set(min_delay=1, max_delay=10)

        def on_connect(
            mqtt_client, userdata, flags, reason_code, properties
        ):
            nonlocal subscription_mid
            subscribed.clear()
            subscription_mid = None

            if stop_requested.is_set():
                return

            if reason_code.is_failure:
                fail(f"Connexion MQTT refusée : {reason_code}.")
                return

            LOGGER.info("Connexion MQTT établie.")

            result, mid = mqtt_client.subscribe(
                TELEMETRY_TOPICS
            )
            if result != mqtt.MQTT_ERR_SUCCESS:
                fail(
                    "Impossible de transmettre la demande "
                    f"d'abonnement MQTT : {result}."
                )
                return

            subscription_mid = mid
            LOGGER.info("Abonnement demandé : %s.", TELEMETRY_TOPICS)

        def on_subscribe(
            mqtt_client, userdata, mid, reason_codes, properties
        ):
            if stop_requested.is_set():
                return

            if mid != subscription_mid:
                fail("Confirmation reçue pour un abonnement inattendu.")
                return

            # Tous les abonnements doivent être accordés en QoS 1.
            if len(reason_codes) != len(TELEMETRY_TOPICS) or any(code != 1 for code in reason_codes):
                fail(
                    "Le broker n'a pas accordé l'abonnement en QoS 1 : "
                    f"{reason_codes}."
                )
                return

            subscribed.set()
            LOGGER.info(
                "Ingestion prête : abonnement confirmé en QoS 1 sur %s.",
                TELEMETRY_TOPICS,
            )

        def acknowledge(mqtt_client, message):
            result = mqtt_client.ack(message.mid, message.qos)
            if result != mqtt.MQTT_ERR_SUCCESS:
                fail(
                    "Impossible d'acquitter le message MQTT "
                    f"{message.mid} : {result}."
                )

        def on_message(mqtt_client, userdata, message):
            if stop_requested.is_set():
                return

            try:
                inserted = ingest_telemetry(
                    database_engine,
                    message.topic,
                    message.payload,
                    retained=message.retain,
                )
            except ValueError as error:
                LOGGER.warning(
                    "Message rejeté sur %s : %s",
                    message.topic,
                    error,
                )
                # Le rejet est définitif : inutile de redélivrer
                # un message dont le contenu est invalide.
                acknowledge(mqtt_client, message)
                return
            except SQLAlchemyError:
                LOGGER.exception(
                    "Échec SQL sur %s : écriture non confirmée. "
                    "Message MQTT non acquitté ; arrêt de l'ingestion.",
                    message.topic,
                )
                fatal_error.set()
                stop_requested.set()
                return
            except Exception:
                # Frontière du callback : rendre l'échec visible
                # au processus principal, puis arrêter le service.
                LOGGER.exception(
                    "Erreur inattendue pendant l'ingestion. "
                    "Message MQTT non acquitté ; arrêt du service."
                )
                fatal_error.set()
                stop_requested.set()
                return

            # Le JSON a déjà été validé par ingest_telemetry().
            event_id = json.loads(message.payload)["event_id"]

            if inserted:
                LOGGER.info("Événement enregistré | événement : %s", event_id)
            else:
                LOGGER.info("Doublon ignoré | événement : %s", event_id)

            # L'insertion est validée, ou le doublon est reconnu.
            acknowledge(mqtt_client, message)

        def on_disconnect(
            mqtt_client, userdata, disconnect_flags, reason_code, properties
        ):
            subscribed.clear()

            if not stop_requested.is_set():
                LOGGER.warning(
                    "Connexion MQTT perdue (%s). "
                    "Ingestion indisponible ; reconnexion automatique.",
                    reason_code,
                )

        def on_connect_fail(mqtt_client, userdata):
            LOGGER.warning(
                "Tentative de connexion MQTT échouée ; nouvel essai prévu."
            )

        client.on_connect = on_connect
        client.on_subscribe = on_subscribe
        client.on_message = on_message
        client.on_disconnect = on_disconnect
        client.on_connect_fail = on_connect_fail

        LOGGER.info("Connexion à Mosquitto sur %s:%s...", host, port)
        client.connect_async(host, port, keepalive=60)

        if client.loop_start() != mqtt.MQTT_ERR_SUCCESS:
            raise RuntimeError("Impossible de démarrer la boucle réseau MQTT.")
        loop_started = True

        deadline = monotonic() + STARTUP_TIMEOUT_S

        while not subscribed.is_set() and not stop_requested.is_set():
            if monotonic() >= deadline:
                fail(
                    "Démarrage impossible : abonnement MQTT non confirmé "
                    "dans le délai de 10 secondes."
                )
                break
            stop_requested.wait(0.1)

        while not stop_requested.wait(0.2):
            pass

        return 1 if fatal_error.is_set() else 0

    except (ValueError, RuntimeError, OSError):
        LOGGER.exception("Impossible de démarrer le service d'ingestion.")
        return 1

    finally:
        stop_requested.set()

        try:
            if client is not None:
                client.disconnect()
                if loop_started:
                    client.loop_stop()
        finally:
            # La boucle réseau est arrêtée avant de libérer le moteur.
            if engine is not None:
                engine.dispose()

            for signum, previous_handler in previous_handlers.items():
                signal.signal(signum, previous_handler)

        LOGGER.info("Service d'ingestion arrêté ; ressources libérées.")


if __name__ == "__main__":
    raise SystemExit(main())
