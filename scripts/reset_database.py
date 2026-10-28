"""Reconstruit la base de serre ; conserve les compteurs d'identifiants."""
import argparse
from pathlib import Path
import subprocess
from greenmind.db.session import DEFAULT_DATABASE_PATH, create_database_engine
from greenmind.identifiers import counter_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, default=DEFAULT_DATABASE_PATH)
    args = parser.parse_args()
    running = subprocess.run(['ps', '-axo', 'command='], capture_output=True, text=True, check=True).stdout
    if any(marker in line for line in running.splitlines() for marker in (
        '-m greenmind.ingestion.main', '-m greenmind.simulator.main', '-m greenmind.api.main',
        'streamlit run src/greenmind/dashboard/app.py')):
        raise RuntimeError('Arrêter les services GreenMind avant de reconstruire la base.')
    path = args.database.resolve()
    if path == counter_path():
        raise ValueError('Le stockage des compteurs ne doit jamais être effacé par ce script.')
    for suffix in ('', '-wal', '-shm'):
        Path(str(path) + suffix).unlink(missing_ok=True)
    engine = create_database_engine(path)
    engine.dispose()
    print(f'Base reconstruite au schéma v3 : {path}. Compteurs conservés.')


if __name__ == '__main__':
    main()
