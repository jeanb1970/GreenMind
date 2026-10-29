"""Démarrer, arrêter ou rejouer les services locaux sans effacer l'historique."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / 'outputs' / 'demo'
REGISTRY = RUN / 'processes.json'


def alive(record):
    result = subprocess.run(['ps', '-p', str(record['pid']), '-o', 'command='], capture_output=True, text=True)
    return result.returncode == 0 and record['marker'] in result.stdout


def stop(records):
    for record in reversed(records):
        if alive(record):
            os.kill(record['pid'], signal.SIGTERM)
    deadline = time.monotonic() + 15
    while any(alive(r) for r in records) and time.monotonic() < deadline:
        time.sleep(0.1)
    if any(alive(r) for r in records):
        raise RuntimeError('Arrêt incomplet ; vérifier les processus avant de relancer.')
    REGISTRY.unlink(missing_ok=True)


def start():
    subprocess.run(['docker', 'compose', 'up', '-d', 'mosquitto'], cwd=ROOT, check=True)
    env = dict(os.environ, PYTHONPATH=str(ROOT / 'src'), GREENMIND_SIMULATION_MODE='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', TOKENIZERS_PARALLELISM='false')
    records = []
    def launch(args, marker, readiness):
        path = RUN / (marker.rsplit('.', 1)[-1] + str(len(records)) + '.log')
        with path.open('w') as log:
            proc = subprocess.Popen([sys.executable] + args, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        records.append({'pid': proc.pid, 'marker': marker})
        REGISTRY.write_text(json.dumps(records))
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                raise RuntimeError(path.read_text()[-3000:])
            if readiness(path):
                return
            time.sleep(0.2)
        raise RuntimeError(f'Démarrage non confirmé : {marker} ; voir {path}')
    try:
        launch(['-m', 'greenmind.ingestion.main'], 'greenmind.ingestion.main', lambda p: 'Ingestion prête' in p.read_text())
        launch(['-m', 'greenmind.simulator.main'], 'greenmind.simulator.main', lambda p: 'Simulateur prêt en pause' in p.read_text())
        launch(['-m', 'greenmind.api.main'], 'greenmind.api.main', lambda p: 'Application startup complete' in p.read_text())
        def dashboard_ready(path):
            try:
                with urlopen('http://127.0.0.1:8501/_stcore/health', timeout=1) as response:
                    return response.status == 200
            except OSError:
                return False
        launch(['-m', 'streamlit', 'run', 'src/greenmind/dashboard/app.py', '--server.address=127.0.0.1', '--server.headless=true'], 'streamlit run src/greenmind/dashboard/app.py', dashboard_ready)
    except Exception:
        stop(records)
        raise
    print('GreenMind : http://127.0.0.1:8501 · API : http://127.0.0.1:8000/docs')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['start', 'stop', 'reset', 'from-scratch'])
    args = parser.parse_args()
    action = args.action
    RUN.mkdir(parents=True, exist_ok=True)
    import fcntl
    with (RUN / 'launcher.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        records = json.loads(REGISTRY.read_text()) if REGISTRY.exists() else []
        if action == 'from-scratch':
            print('Effacement de la base de serre ET des compteurs. Les services seront arrêtés.')
            if input('Saisir EFFACER pour confirmer : ').strip() != 'EFFACER':
                print('Annulé ; aucune modification.')
                return
            stop(records)
            env = dict(os.environ, PYTHONPATH=str(ROOT / 'src'))
            subprocess.run([sys.executable, str(ROOT / 'scripts/reset_database.py'), '--all'],
                           cwd=ROOT, env=env, check=True)
            print('Base vide et compteurs effacés. Utiliser start pour démarrer une nouvelle démo.')
            return
        if action == 'start' and any(alive(r) for r in records):
            raise RuntimeError('Une démo est déjà lancée.')
        if action in ('stop', 'reset'):
            stop(records)
        if action in ('start', 'reset'):
            start()
    print('Historique conservé ; chaque redémarrage crée une nouvelle simulation.')


if __name__ == '__main__':
    main()
