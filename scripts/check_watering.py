"""Recette B5 : trois arroseurs via API, Mosquitto, simulateur et SQLite temporaire.

Le broker local doit fonctionner. Aucun fichier de données du projet n'est effacé.
Les commandes ciblent seulement la session créée par cette recette.
"""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
from time import monotonic, sleep
from uuid import uuid4
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from greenmind.api.app import create_app
from greenmind.api.dependencies import get_db, get_publisher, MqttPublisher
from greenmind.db.models import GreenhouseReading, WateringCommandRow
from greenmind.db.session import create_database_engine
from greenmind.schemas import WateringCommand

ROOT = Path(__file__).resolve().parents[1]


def wait_for(predicate, description, timeout=15):
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        result = predicate()
        if result:
            return result
        sleep(0.05)
    raise RuntimeError(f'Délai dépassé : {description}.')


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    processes, logs = [], []
    db, passed = None, False
    with tempfile.TemporaryDirectory(prefix='greenmind-b5-') as directory:
        directory = Path(directory)
        try:
            path = directory / 'watering.sqlite'
            db = create_database_engine(path)
            env = dict(os.environ, PYTHONPATH=str(ROOT / 'src'), GREENMIND_DATABASE_PATH=str(path))
            def start(module, name):
                logfile = directory / f'{name}.log'
                handle = logfile.open('w')
                logs.append((logfile, handle))
                process = subprocess.Popen([sys.executable, '-m', module], cwd=ROOT, env=env,
                    stdout=handle, stderr=subprocess.STDOUT)
                processes.append(process)
                return logfile
            ingestion_log = start('greenmind.ingestion.main', 'ingestion')
            wait_for(lambda: 'Ingestion prête' in ingestion_log.read_text(), 'abonnement ingestion')
            start('greenmind.simulator.main', 'simulateur')
            def initial_ready():
                with Session(db) as session:
                    rows = list(session.scalars(select(GreenhouseReading).where(
                        GreenhouseReading.measurement_origin == 'initial')))
                    return rows if len(rows) == 3 else None
            wait_for(initial_ready, 'trois bacs initiaux')
            app = create_app()
            publisher = MqttPublisher()
            app.dependency_overrides[get_db] = lambda: db
            app.dependency_overrides[get_publisher] = lambda: publisher
            with TestClient(app) as client:
                def plants():
                    return {p['plant_id']: p for p in client.get('/api/v1/plants').json()}
                def revision():
                    return max(p['state_revision'] for p in plants().values())
                def inject(plant, moisture):
                    response = client.post('/api/v1/simulation/controls', json={
                        'action': 'SET_SOIL_MOISTURE', 'plant_id': plant,
                        'value': moisture, 'expected_revision': revision(),
                    })
                    require(response.status_code == 202, f'Forçage refusé : {response.text}')
                    control_id = response.json()['control_id']
                    wait_for(lambda: client.get(f'/api/v1/simulation/controls/{control_id}').json()['status'] == 'APPLIED', 'forçage appliqué')
                    wait_for(lambda: plants()[plant]['soil_moisture_sim_pct'] == moisture, 'mesure forcée')

                # Le broker confirme le transport, mais aucun simulateur ne
                # reçoit cette publication sur un topic de test sans abonné.
                class NoConsumerPublisher:
                    def publish_watering(self, plant, payload):
                        publisher._publish('greenmind/v2/tests/no-consumer', payload)
                inject('thym_01', 10.0)
                proposal = client.post('/api/v1/plants/thym_01/watering-proposals', json={}).json()
                app.dependency_overrides[get_publisher] = lambda: NoConsumerPublisher()
                pending = client.post('/api/v1/plants/thym_01/watering-commands', json={
                    'proposal_id': proposal['proposal_id'], 'command_id': str(uuid4()),
                })
                require(pending.status_code == 202, f'Confirmation de test refusée : {pending.text}')
                app.dependency_overrides[get_publisher] = lambda: publisher
                timeout_id = pending.json()['command_id']
                wait_for(lambda: client.get(f'/api/v1/watering-commands/{timeout_id}').json()['status'] == 'TIMED_OUT',
                         'timeout sans acquittement métier')
                blocked = client.post('/api/v1/simulation/controls', json={'action': 'ADVANCE', 'expected_revision': revision()})
                require(blocked.status_code == 409, 'Mutation acceptée pendant une exécution incertaine.')
                with Session(db) as session:
                    expired = session.get(WateringCommandRow, timeout_id).payload
                publisher.publish_watering('thym_01', expired)
                wait_for(lambda: client.get(f'/api/v1/watering-commands/{timeout_id}').json()['status'] == 'REJECTED',
                         'refus tardif corrélé de la commande expirée')
                print('OK : PUBACK sans effet, timeout, mutations bloquées et refus tardif corrélé.', flush=True)
                for plant, moisture in {'basilic_01': 20.0, 'thym_01': 10.0, 'romarin_01': 15.0}.items():
                    inject(plant, moisture)
                    before = plants()
                    state_before = client.get('/api/v1/simulation').json()
                    response = client.post(f'/api/v1/plants/{plant}/watering-proposals', json={})
                    require(response.status_code == 201, f'Proposition refusée : {response.text}')
                    proposal = response.json()
                    require(plants()[plant]['state_revision'] == before[plant]['state_revision'], 'La proposition a modifié la serre.')
                    payload = {'proposal_id': proposal['proposal_id'], 'command_id': str(uuid4())}
                    url = f'/api/v1/plants/{plant}/watering-commands'
                    response = client.post(url, json=payload)
                    require(response.status_code == 202, f'Confirmation refusée : {response.text}')
                    key = payload['command_id']
                    def executed():
                        data = client.get(f'/api/v1/watering-commands/{key}').json()
                        if data['status'] in ('REJECTED', 'TIMED_OUT'):
                            raise RuntimeError(f'Arrosage non exécuté : {data}')
                        return data if data['status'] == 'EXECUTED' and not data['measurement_pending'] else None
                    result = wait_for(executed, 'acquittement métier et mesure après arrosage')
                    require(client.post(url, json=payload).status_code == 202, 'Rejeu REST refusé.')
                    with Session(db) as session:
                        command = WateringCommand.model_validate_json(session.get(WateringCommandRow, key).payload)
                    # Vrai doublon MQTT : le moteur doit republier son résultat sans effet supplémentaire.
                    publisher.publish_watering(plant, command.model_dump_json())
                    sleep(0.3)
                    after = plants()
                    require(after[plant]['state_revision'] == result['resulting_revision'], 'Doublon appliqué deux fois.')
                    require(after[plant]['soil_moisture_sim_pct'] == proposal['soil_moisture_after_pct'], 'Gain incorrect.')
                    require(not after[plant]['has_active_alert'], 'Alerte non clôturée après arrosage.')
                    require(all(after[p]['soil_moisture_sim_pct'] == before[p]['soil_moisture_sim_pct'] for p in before if p != plant), 'Un autre bac a été modifié.')
                    require(client.get('/api/v1/simulation').json()['simulated_tick'] == state_before['simulated_tick'], 'Arrosage ayant avancé l’heure météo.')
                    events = client.get('/api/v1/events', params={'plant_id': plant}).json()
                    require(sum(e['event_type'] == 'WATERING_EXECUTED' for e in events) == 1, 'Journal d’exécution dupliqué.')
                    require(client.post(url, json={'proposal_id': proposal['proposal_id'], 'command_id': str(uuid4())}).status_code == 409, 'Proposition consommée réutilisable.')
                    inject(plant, moisture)
                    require(client.post(f'/api/v1/plants/{plant}/watering-proposals', json={}).status_code == 409, 'Repos du bac non respecté.')
                    print(f'OK : {plant}, proposition → confirmation → effet unique → ACK → mesure ; doublons, isolation et repos vérifiés.', flush=True)
                # Refus effectif côté simulateur d'une commande expirée.
                plant = 'basilic_01'
                from datetime import datetime, timedelta, timezone
                stale = WateringCommand(
                    command_id=uuid4(), run_id=command.run_id, plant_id=plant,
                    actuator_id='arroseur_basilic', duration_sim_s=10.0,
                    expected_revision=revision(), requested_at=datetime.now(timezone.utc)-timedelta(seconds=20),
                    expires_at=datetime.now(timezone.utc)-timedelta(seconds=10),
                )
                # L'événement rejeté reste traçable, même pour un producteur de test sans intention REST.
                from greenmind.db.models import WateringEventRow
                publisher.publish_watering(plant, stale.model_dump_json())
                def rejected():
                    with Session(db) as session:
                        row = session.scalar(select(WateringEventRow).where(WateringEventRow.command_id == str(stale.command_id)))
                        return row if row else None
                event = wait_for(rejected, 'refus MQTT d’une commande expirée')
                from greenmind.schemas import WateringEvent
                require(WateringEvent.model_validate_json(event.payload).status == 'REJECTED', 'Commande expirée acceptée.')
                require(all(p.poll() is None for p in processes), 'Un service a quitté prématurément.')
                passed = True
        except Exception as error:
            print(f'ÉCHEC de recette B5 : {error}', flush=True)
            for logfile, handle in logs:
                handle.flush()
                print(logfile.read_text()[-5000:])
        finally:
            for process in reversed(processes):
                if process.poll() is None:
                    process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
                    passed = False
                if process.returncode != 0:
                    passed = False
            for _, handle in logs:
                handle.close()
            if db:
                db.dispose()
    if passed:
        print('TEST RÉUSSI : B5, trois arroseurs via MQTT réel et arrêt propre des services.')
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
