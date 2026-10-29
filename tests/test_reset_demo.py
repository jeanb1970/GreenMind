"""La reconstruction complète est testée uniquement sur des fichiers temporaires."""
import runpy
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace
import pytest
from greenmind.db.session import create_database_engine
from greenmind.identifiers import next_id

ROOT = Path(__file__).resolve().parents[1]


def test_reset_all_on_temporary_files(tmp_path, monkeypatch):
    database = tmp_path / 'greenhouse.sqlite'
    counters = tmp_path / 'counters.sqlite'
    monkeypatch.setenv('GREENMIND_IDENTIFIERS_PATH', str(counters))
    monkeypatch.setenv('GREENMIND_DATABASE_PATH', str(database))
    db = create_database_engine(database)
    db.dispose()
    next_id('event')
    monkeypatch.setattr('subprocess.run', lambda *a, **k: SimpleNamespace(stdout='', returncode=0))
    monkeypatch.setattr(sys, 'argv', ['reset_database.py', '--all'])
    runpy.run_path(str(ROOT / 'scripts/reset_database.py'), run_name='__main__')
    assert not counters.exists()
    with sqlite3.connect(database) as sql:
        assert sql.execute('SELECT COUNT(*) FROM sensor_readings').fetchone()[0] == 0
    assert next_id('event') == 'Evenement_000001'


def test_reset_refuses_running_services(tmp_path, monkeypatch):
    database = tmp_path / 'sentinel.sqlite'
    database.write_bytes(b'untouched')
    monkeypatch.setenv('GREENMIND_DATABASE_PATH', str(database))
    monkeypatch.setattr('subprocess.run', lambda *a, **k: SimpleNamespace(stdout='python -m greenmind.api.main'))
    monkeypatch.setattr(sys, 'argv', ['reset_database.py', '--all'])
    with pytest.raises(RuntimeError, match='Arrêter'):
        runpy.run_path(str(ROOT / 'scripts/reset_database.py'), run_name='__main__')
    assert database.read_bytes() == b'untouched'


def test_from_scratch_cancel_does_not_stop_services(monkeypatch, tmp_path):
    scope = runpy.run_path(str(ROOT / 'scripts/demo.py'))
    main = scope['main']
    main.__globals__.update(RUN=tmp_path, REGISTRY=tmp_path / 'processes.json',
        stop=lambda *a: pytest.fail('aucun arrêt si annulation'))
    monkeypatch.setattr('builtins.input', lambda *a: 'non')
    monkeypatch.setattr(sys, 'argv', ['demo.py', 'from-scratch'])
    main()
