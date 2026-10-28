"""Transport réel de la serre ; un seul thread applique les mutations."""
import fcntl
import logging
import os
import signal
from pathlib import Path
from queue import Queue, Empty, Full
from threading import Event
from time import monotonic
from uuid import uuid4
import paho.mqtt.client as mqtt
from greenmind.greenhouse_config import load_greenhouse_config
from greenmind.schemas import SimulationControl, WateringCommand, parse_v3, telemetry_for_snapshot
from greenmind.simulator.controls import ControlProcessor
from greenmind.simulator.watering import WateringProcessor
from greenmind.simulator.engine import SimulationEngine
from greenmind.simulator.weather import load_weather

ROOT = Path(__file__).resolve().parents[3]
CONTROL_TOPIC = "greenmind/v3/simulation/controls"
EVENT_TOPIC = "greenmind/v3/simulation/events"
LOGGER = logging.getLogger("greenmind.simulator")

def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    stop, ready, failed = Event(), Event(), Event()
    pending = Queue(maxsize=100)
    client = lock = None
    loop_started = False
    previous_handlers = {}
    try:
        lock_path = Path(os.environ.get("GREENMIND_SIMULATOR_LOCK", str(ROOT / "outputs/run/simulator.lock")))
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock = lock_path.open("a+")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("Un simulateur GreenMind utilise déjà ce verrou.") from None
        for signum in (signal.SIGINT, signal.SIGTERM):
            previous_handlers[signum] = signal.signal(signum, lambda *_: stop.set())
        config = load_greenhouse_config(ROOT / "config/greenhouse.yaml")
        engine = SimulationEngine(config,
                                  load_weather(ROOT / "data/fixtures/weather_greenhouse_day.csv"))
        processor = ControlProcessor(engine)
        watering = WateringProcessor(engine, config)
        host = os.environ.get("GREENMIND_MQTT_HOST", "127.0.0.1").strip()
        port = int(os.environ.get("GREENMIND_MQTT_PORT", "1883"))
        if not host or not 1 <= port <= 65535:
            raise ValueError("Adresse ou port MQTT invalide.")
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                             client_id=f"greenmind-simulator-{uuid4().hex[:8]}",
                             clean_session=True, protocol=mqtt.MQTTv311)
        client.connect_timeout = 5.0
        def on_connect(c, userdata, flags, reason_code, properties):
            if reason_code.is_failure:
                failed.set()
            else:
                rc, _ = c.subscribe([(CONTROL_TOPIC, 1), ('greenmind/v3/plants/+/commands', 1)])
                if rc != mqtt.MQTT_ERR_SUCCESS:
                    failed.set()
        def on_subscribe(c, userdata, mid, reason_codes, properties):
            if len(reason_codes) == 2 and all(code == 1 for code in reason_codes):
                ready.set()
            else:
                failed.set()
        def on_message(c, userdata, message):
            try:
                if message.retain:
                    raise ValueError("Un contrôle retained est interdit.")
                if message.topic == CONTROL_TOPIC:
                    command = parse_v3(SimulationControl, message.payload)
                else:
                    command = parse_v3(WateringCommand, message.payload)
                    if message.topic != f"greenmind/v3/plants/{command.plant_id}/commands":
                        raise ValueError("Topic d'arrosage incohérent avec le bac ciblé.")
                pending.put_nowait(command)
            except ValueError as error:
                LOGGER.warning("Contrôle rejeté : %s", error)
            except Full:
                LOGGER.error("File de contrôles saturée ; arrêt sûr du simulateur.")
                failed.set()
        def on_disconnect(c, userdata, flags, reason_code, properties):
            ready.clear()
            if not stop.is_set():
                LOGGER.error("Connexion MQTT perdue ; reprise automatique du scénario interdite.")
                failed.set()
        client.on_connect, client.on_subscribe = on_connect, on_subscribe
        client.on_message, client.on_disconnect = on_message, on_disconnect
        client.connect_async(host, port, keepalive=60)
        if client.loop_start() != mqtt.MQTT_ERR_SUCCESS:
            raise RuntimeError("Impossible de démarrer la boucle MQTT.")
        loop_started = True
        deadline = monotonic() + 10
        while not ready.is_set() and not stop.is_set():
            if failed.is_set() or monotonic() >= deadline:
                raise RuntimeError("Abonnement aux contrôles MQTT non confirmé en 10 secondes.")
            stop.wait(0.05)
        def publish(topic, message):
            result = client.publish(topic, message.model_dump_json(), qos=1, retain=False)
            if result.rc != mqtt.MQTT_ERR_SUCCESS:
                raise RuntimeError("Publication MQTT refusée.")
            result.wait_for_publish(timeout=5)
            if not result.is_published():
                raise RuntimeError("Publication non confirmée par le broker ; arrêt du scénario.")
        def publish_state(messages, event):
            for message in messages:
                publish(f"greenmind/v3/plants/{message.plant_id}/telemetry", message)
            publish(EVENT_TOPIC, event)
        if stop.is_set():
            return 0
        publish_state(telemetry_for_snapshot(engine.snapshot(), "initial"), processor.state_event())
        LOGGER.info("Simulateur prêt en pause | exécution : %s", engine.snapshot().simulation)
        next_heartbeat = monotonic() + 5
        while not stop.wait(0.05):
            if failed.is_set():
                raise RuntimeError("Transport MQTT indisponible ; redémarrage contrôlé requis.")
            try:
                control = pending.get_nowait()
            except Empty:
                control = None
            if control is not None:
                if isinstance(control, WateringCommand):
                    result = watering.apply(control)
                    # ACK d'abord : le suivi distingue explicitement une mesure
                    # encore en transit d'une exécution non confirmée.
                    publish(f"greenmind/v3/plants/{control.plant_id}/events", result.event)
                    for message in result.telemetry:
                        publish(f"greenmind/v3/plants/{message.plant_id}/telemetry", message)
                    publish(EVENT_TOPIC, processor.state_event())
                    LOGGER.info("Arrosage %s : %s", control.command_id, result.event.status)
                else:
                    result = processor.apply(control)
                    publish_state(result.telemetry, result.event)
                    LOGGER.info("Contrôle %s : %s", control.control_id, result.event.status)
            transition = engine.poll()
            if transition is not None:
                publish_state(telemetry_for_snapshot(transition.after, "calcul_horaire"), processor.state_event())
                next_heartbeat = monotonic() + 5
            elif monotonic() >= next_heartbeat:
                publish_state(telemetry_for_snapshot(engine.snapshot(), "signal_presence"), processor.state_event())
                next_heartbeat = monotonic() + 5
        return 0
    except (ValueError, RuntimeError, OSError):
        LOGGER.exception("Arrêt du simulateur sur erreur.")
        return 1
    finally:
        stop.set()
        if client is not None:
            client.disconnect()
            if loop_started:
                client.loop_stop()
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)
        if lock is not None:
            lock.close()
        LOGGER.info("Simulateur arrêté ; ressources libérées.")
