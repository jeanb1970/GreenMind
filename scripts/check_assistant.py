"""Recette B8 : API, MiniLM/FAISS et Qwen3 local, sans mutation de la serre."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
from time import monotonic, sleep
from unittest.mock import patch
from fastapi.testclient import TestClient
from greenmind.api.app import create_app
from greenmind.api.dependencies import get_db
from greenmind.db.models import Base
from greenmind.db.readings import save_message
from greenmind.db.session import create_database_engine
from greenmind.identifiers import next_id, next_simulation
from greenmind.schemas import TelemetryV3


def counts(db):
    with db.connect() as connection:
        return {t.name: connection.exec_driver_sql(f'SELECT COUNT(*) FROM {t.name}').scalar() for t in Base.metadata.sorted_tables}


def main():
    with tempfile.TemporaryDirectory(prefix='greenmind-b8-') as temporary:
        temporary = Path(temporary)
        with patch.dict(os.environ, {'GREENMIND_IDENTIFIERS_PATH': str(temporary / 'ids.sqlite')}):
            db = create_database_engine(temporary / 'assistant.sqlite')
            try:
                now = datetime.now(timezone.utc)
                virtual = datetime(2026, 7, 9, 22, tzinfo=timezone.utc)
                simulation = next_simulation()
                moisture = {'basilic': 32.0, 'thym': 18.0, 'romarin': 22.0}
                for plant, value in moisture.items():
                    save_message(db, TelemetryV3(event_id=next_id('event'), simulation=simulation,
                        plant_id=plant, observed_at=virtual, simulated_at=virtual, emitted_at=now,
                        heure_virtuelle=0, current_state=1, paused=True, day_complete=False,
                        air_temperature_c=22.0, air_humidity_pct=60.0, soil_moisture_pct=value,
                        arroseur_active=False, provenance='meteo_simulee', measurement_origin='modification_manuelle'))
                before = counts(db)
                app = create_app()
                app.dependency_overrides[get_db] = lambda: db
                with TestClient(app) as client:
                    latencies = []
                    for plant in moisture:
                        start = monotonic()
                        with ThreadPoolExecutor(max_workers=1) as pool:
                            pending = pool.submit(client.post, '/api/v1/assistant/ask', json={
                                'plant_id': plant, 'question': f'Quels sont les besoins en eau et en drainage du {plant} en pot ?'})
                            wait_deadline = monotonic() + 5
                            while client.app.state.assistant._task is None or client.app.state.assistant._task.done():
                                if pending.done() or monotonic() > wait_deadline:
                                    break
                                sleep(0.01)
                            read_start = monotonic()
                            response = client.get('/api/v1/plants')
                            read_duration = monotonic() - read_start
                            if response.status_code != 200 or read_duration > 3:
                                raise RuntimeError('La génération bloque la consultation IoT.')
                            answer = pending.result(timeout=45)
                        duration = monotonic() - start
                        data = answer.json()
                        if answer.status_code != 200 or data.get('status') != 'répondu':
                            raise RuntimeError(f'Génération réelle non validée : {data}')
                        if data['facts']['soil_moisture_pct'] != moisture[plant] or data['action_executed']:
                            raise RuntimeError('Faits inexacts ou action annoncée.')
                        if data['facts']['measurement_origin'] != 'modification_manuelle' or not data['sources']:
                            raise RuntimeError('Origine de mesure ou sources manquantes.')
                        for source in data['sources']:
                            root = Path(__file__).resolve().parents[1]
                            if source['plant_id'] != plant or source['excerpt'] not in (root / source['local_path']).read_text():
                                raise RuntimeError('Citation non traçable.')
                        latencies.append(duration)
                        print(json.dumps(dict(plant_id=plant, duration_s=round(duration, 2),
                            iot_read_s=round(read_duration, 3), explanation=data['explanation'],
                            source_ids=[s['chunk_id'] for s in data['sources']]), ensure_ascii=False), flush=True)
                    for question, expected in [('Arrose ce bac maintenant', 'action_non_exécutée'),
                        ('Quel diagnostic certain de maladie ?', 'sources_insuffisantes'),
                        ('Quelle est la capitale du Japon ?', 'sources_insuffisantes')]:
                        data = client.post('/api/v1/assistant/ask', json={'plant_id': 'thym', 'question': question}).json()
                        if data['status'] != expected or data['action_executed']:
                            raise RuntimeError('Refus attendu absent.')
                    print(f'OK : génération réelle sur trois plantes ; latences {latencies}.', flush=True)
                # Simuler une panne du seul service de génération, sans toucher
                # au serveur Ollama de l'utilisateur ni à ses autres modèles.
                with patch.dict(os.environ, {'GREENMIND_OLLAMA_URL': 'http://127.0.0.1:1'}):
                    app = create_app()
                    app.dependency_overrides[get_db] = lambda: db
                    with TestClient(app) as client:
                        data = client.post('/api/v1/assistant/ask', json={'plant_id': 'thym', 'question': 'Pourquoi ce substrat doit-il être drainant ?'}).json()
                        if data['status'] != 'indisponible' or data['facts']['soil_moisture_pct'] != 18.0:
                            raise RuntimeError('La panne IA ne conserve pas les faits du bac.')
                        if client.get('/api/v1/plants').status_code != 200:
                            raise RuntimeError('La panne IA rend la serre indisponible.')
                if counts(db) != before:
                    raise RuntimeError('Une question a modifié la base métier.')
                print('TEST RÉUSSI : B8, réponses sourcées locales, faits exacts, panne isolée et aucune mutation.', flush=True)
            finally:
                db.dispose()


if __name__ == '__main__':
    main()
