"""Recette réelle B3 : deux processus, broker local et SQLite temporaire.

Le broker doit déjà fonctionner. Les contrôles visent seulement la session
créée par ce script ; aucun arrêt du broker ni effacement de la base projet.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from threading import Event
from time import monotonic, sleep
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4
import paho.mqtt.client as mqtt
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from greenmind.db.models import GreenhouseReading, SimulationEventRow
from greenmind.db.session import create_database_engine
from greenmind.db.readings import latest_reading
from greenmind.schemas import SimulationControl, TelemetryV2

ROOT = Path(__file__).resolve().parents[1]

def wait_for(predicate, description, timeout=15):
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        result = predicate()
        if result:
            return result
        sleep(0.05)
    raise RuntimeError(f'Délai dépassé : {description}.')

def main():
    processes = []
    client = db = None
    logs = []
    passed = False
    with tempfile.TemporaryDirectory(prefix='greenmind-b3-') as directory:
        directory = Path(directory)
        try:
            path = directory / 'test.sqlite'
            db = create_database_engine(path)
            env = dict(os.environ, PYTHONPATH=str(ROOT/'src'), GREENMIND_DATABASE_PATH=str(path))
            def start(module, name):
                logfile = directory / f'{name}.log'
                handle = logfile.open('w')
                logs.append((logfile, handle))
                process = subprocess.Popen([sys.executable, '-m', module], cwd=ROOT, env=env,
                                           stdout=handle, stderr=subprocess.STDOUT)
                processes.append(process)
                return process, logfile
            ingestion, ingestion_log = start('greenmind.ingestion.main', 'ingestion')
            wait_for(lambda: 'Ingestion prête' in ingestion_log.read_text(), 'abonnement ingestion')
            simulator, simulator_log = start('greenmind.simulator.main', 'simulateur')
            def initial_rows():
                with Session(db) as session:
                    rows = list(session.scalars(select(GreenhouseReading).where(
                        GreenhouseReading.measurement_origin == 'initial')))
                    return rows if len(rows) == 3 else None
            rows = wait_for(initial_rows, 'trois mesures initiales en SQL')
            run_id = UUID(rows[0].run_id)
            if {r.plant_id for r in rows} != {'basilic_01','thym_01','romarin_01'}:
                raise RuntimeError('Les trois bacs attendus ne sont pas présents.')
            if any(r.run_id != str(run_id) or r.simulated_tick != 0 or not r.paused for r in rows):
                raise RuntimeError('État initial incohérent.')
            print('OK : trois mesures initiales, même session, pause au pas 0.', flush=True)
            connected = Event()
            client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f'greenmind-check-{uuid4().hex[:8]}')
            def on_connect(c, userdata, flags, reason, properties):
                if not reason.is_failure: connected.set()
            client.on_connect = on_connect
            client.connect_async(os.environ.get('GREENMIND_MQTT_HOST','127.0.0.1'),
                                 int(os.environ.get('GREENMIND_MQTT_PORT','1883')))
            client.loop_start()
            if not connected.wait(10): raise RuntimeError('Connexion du contrôleur impossible.')
            def publish(topic, payload):
                info = client.publish(topic, payload, qos=1, retain=False)
                info.wait_for_publish(timeout=5)
                if not info.is_published(): raise RuntimeError('Publication de contrôle non confirmée.')
            def require_reading(plant_id: str) -> GreenhouseReading:
                reading = latest_reading(db, run_id, plant_id)
                if reading is None:
                    raise RuntimeError(f"Mesure introuvable en base pour {plant_id}.")
                return reading

            def request(action, **kwargs):
                now = datetime.now(timezone.utc)
                return SimulationControl(control_id=uuid4(), run_id=run_id, action=action,
                    expected_revision=require_reading('basilic_01').state_revision,
                    requested_at=now, expires_at=now+timedelta(seconds=30), **kwargs)
            def result_of(command):
                with Session(db) as session:
                    row = session.scalar(select(SimulationEventRow).where(
                        SimulationEventRow.control_id == str(command.control_id)))
                    return json.loads(row.payload) if row else None
            def send(command):
                publish('greenmind/v2/simulation/controls',command.model_dump_json())
                return wait_for(lambda: result_of(command), 'résultat métier persisté')
            advance = request('ADVANCE')
            if send(advance)['status'] != 'APPLIED': raise RuntimeError('Avance refusée.')
            send(advance)
            wait_for(lambda: all((r := latest_reading(db, run_id, p)) is not None and r.simulated_tick == 1
                                for p in ('basilic_01', 'thym_01', 'romarin_01')), 'pas 1 des trois bacs')
            sleep(0.3)
            if require_reading('basilic_01').simulated_tick != 1:
                raise RuntimeError('Doublon de contrôle appliqué deux fois.')
            with Session(db) as session:
                n = session.scalar(select(func.count()).select_from(SimulationEventRow).where(
                    SimulationEventRow.control_id == str(advance.control_id)))
                if n != 1: raise RuntimeError('Acquittement non dédoublonné.')
            print('OK : avance MQTT + acquittement SQL ; doublon sans deuxième effet.', flush=True)
            before = {p: require_reading(p).soil_moisture_sim_pct for p in ('basilic_01', 'thym_01', 'romarin_01')}
            injection = request('SET_SOIL_MOISTURE',plant_id='thym_01',value=18.0)
            if send(injection)['status'] != 'APPLIED': raise RuntimeError('Injection refusée.')
            for plant in before:
                expected = 18.0 if plant == 'thym_01' else before[plant]
                if require_reading(plant).soil_moisture_sim_pct != expected:
                    raise RuntimeError('Injection non isolée.')
            stale = request('ADVANCE').model_copy(update={'expected_revision':0})
            if send(stale)['status'] != 'REJECTED': raise RuntimeError('Révision périmée acceptée.')
            print('OK : injection isolée au thym ; ancienne révision refusée.', flush=True)
            sample = require_reading('basilic_01')
            data = {name:getattr(sample,name) for name in TelemetryV2.model_fields}
            data['event_id'] = str(uuid4())
            data['emitted_at'] = datetime.now(timezone.utc).isoformat()
            bad_id = str(uuid4())
            topic = 'greenmind/v2/plants/basilic_01/telemetry'
            publish(topic,json.dumps(data | {'event_id':bad_id,'soil_moisture_sim_pct':101}))
            for _ in range(2): publish(topic,json.dumps(data))
            def valid_present():
                with Session(db) as session: return session.get(GreenhouseReading,data['event_id']) is not None
            wait_for(valid_present,'mesure valide après rejet')
            with Session(db) as session:
                if session.get(GreenhouseReading,bad_id): raise RuntimeError('Mesure invalide enregistrée.')
            print('OK : mesure invalide rejetée, message suivant enregistré et dédoublonné.', flush=True)
            wait_for(lambda: (r := latest_reading(db, run_id, 'thym_01')) is not None and r.measurement_origin == 'heartbeat',
                     'présence en pause', 10)
            if require_reading('thym_01').soil_moisture_sim_pct != 18:
                raise RuntimeError('Dessèchement pendant la pause.')
            resume = request('RESUME')
            if send(resume)['status'] != 'APPLIED': raise RuntimeError('Reprise refusée.')
            wait_for(lambda: (r := latest_reading(db, run_id, 'thym_01')) is not None and r.simulated_tick == 2,
                     'évolution automatique', 10)
            if send(request('PAUSE'))['status'] != 'APPLIED': raise RuntimeError('Pause refusée.')
            print('OK : présence en pause, reprise automatique et nouvelle pause.', flush=True)
            if any(p.poll() is not None for p in processes): raise RuntimeError('Un service a quitté prématurément.')
            passed = True
        except Exception as error:
            print(f'ÉCHEC de recette B3 : {error}', flush=True)
            for path, handle in logs:
                handle.flush()
                print(path.read_text()[-5000:])
        finally:
            if client:
                client.disconnect()
                client.loop_stop()
            for process in reversed(processes):
                if process.poll() is None: process.terminate()
                try: process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
                    passed=False
                if process.returncode != 0: passed=False
            for _, handle in logs: handle.close()
            if db: db.dispose()
    if passed: print('TEST RÉUSSI : pipeline réel des trois bacs et arrêt propre des deux processus.')
    return 0 if passed else 1

if __name__=='__main__':
    raise SystemExit(main())
