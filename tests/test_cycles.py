"""Cycles répétés : état continu, horloge météo fixe et transport idempotent."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from greenmind.identifiers import next_id
from greenmind.greenhouse_config import load_greenhouse_config
from greenmind.simulator.weather import load_weather
from greenmind.simulator.engine import SimulationEngine
from greenmind.simulator.controls import ControlProcessor
from greenmind.schemas import SimulationControl, telemetry_for_snapshot, parse_v3, TelemetryV3
from greenmind.db.session import create_database_engine
from greenmind.db.readings import save_message, recent_readings
from greenmind.db.models import GreenhouseReading
from greenmind.dashboard.charts import moisture_chart

ROOT = Path(__file__).resolve().parents[1]


def test_three_cycles_continuity_transport_and_chart(tmp_path):
    engine = SimulationEngine(load_greenhouse_config(ROOT / 'config/greenhouse.yaml'),
                              load_weather(ROOT / 'data/fixtures/weather_greenhouse_day.csv'))
    processor = ControlProcessor(engine)
    db = create_database_engine(tmp_path / 'cycles.sqlite')
    initial = engine.snapshot()
    def persist(origin):
        for message in telemetry_for_snapshot(engine.snapshot(), origin):
            save_message(db, parse_v3(TelemetryV3, message.model_dump_json()))
    persist('initial')
    with pytest.raises(ValueError):
        engine.next_day()
    for cycle in range(1, 4):
        assert engine.snapshot().cycle == cycle
        assert engine.snapshot().weather == initial.weather
        for _ in range(24):
            engine.advance_one_hour()
            persist('calcul_horaire')
        end = engine.snapshot()
        assert end.paused and end.day_complete
        if cycle == 3:
            break
        now = datetime.now(timezone.utc)
        command = SimulationControl(control_id=next_id('control'), simulation=end.simulation,
            expected_state=end.current_state, action='jour_suivant', requested_at=now,
            expires_at=now + timedelta(seconds=30))
        result = processor.apply(command)
        assert result.event.status == 'appliqué'
        assert processor.apply(command) == result
        start = engine.snapshot()
        assert start.soil == end.soil and start.simulation == end.simulation
        assert start.cycle == cycle + 1 and start.current_state == end.current_state + 1
        assert start.heure_virtuelle == 0 and start.paused and not start.day_complete
        assert start.simulated_at == initial.simulated_at
        for message in result.telemetry:
            save_message(db, message)
        stale = command.model_copy(update={'control_id': next_id('control')})
        assert processor.apply(stale).event.status == 'refusé'
    readings = recent_readings(db, initial.simulation, 'basilic', 1000, include_presence=False)
    assert len(readings) == 75
    assert {r.cycle for r in readings} == {1, 2, 3}
    chart = moisture_chart([dict(plant_id=r.plant_id, cycle=r.cycle,
        heure_virtuelle=r.heure_virtuelle, soil_moisture_pct=r.soil_moisture_pct,
        current_state=r.current_state, emitted_at=r.emitted_at, event_id=r.event_id,
        measurement_origin=r.measurement_origin) for r in readings]).to_dict()
    rows = chart['data']['values'] if 'values' in chart['data'] else chart['datasets'][chart['data']['name']]
    assert max(r['heures_cumulees'] for r in rows) == 72
    assert chart['encoding']['x']['field'] == 'heures_cumulees'
    db.dispose()


def test_additive_migration_keeps_existing_rows(tmp_path):
    path = tmp_path / 'old.sqlite'
    db = create_database_engine(path)
    engine = SimulationEngine(load_greenhouse_config(ROOT / 'config/greenhouse.yaml'),
                              load_weather(ROOT / 'data/fixtures/weather_greenhouse_day.csv'))
    message = telemetry_for_snapshot(engine.snapshot(), 'initial')[0]
    save_message(db, message)
    db.dispose()
    with sqlite3.connect(path) as sql:
        sql.execute('ALTER TABLE sensor_readings DROP COLUMN cycle')
    migrated = create_database_engine(path)
    with Session(migrated) as session:
        row = session.scalar(select(GreenhouseReading))
        assert row.event_id == message.event_id and row.cycle == 1
        assert row.soil_moisture_pct == message.soil_moisture_pct
    migrated.dispose()


def test_rest_next_day_is_applied_once(tmp_path):
    from fastapi.testclient import TestClient
    from greenmind.api.app import create_app
    from greenmind.api.dependencies import get_db, get_publisher
    from greenmind.schemas import SimulationControl
    config = load_greenhouse_config(ROOT / 'config/greenhouse.yaml')
    engine = SimulationEngine(config, load_weather(ROOT / 'data/fixtures/weather_greenhouse_day.csv'))
    for _ in range(24):
        engine.advance_one_hour()
    end = engine.snapshot()
    db = create_database_engine(tmp_path / 'api.sqlite')
    for m in telemetry_for_snapshot(end, 'calcul_horaire'):
        save_message(db, m)
    processor = ControlProcessor(engine)
    class Publisher:
        def publish_control(self, payload):
            result = processor.apply(parse_v3(SimulationControl, payload))
            for message in result.telemetry:
                save_message(db, message)
            save_message(db, result.event)
    app = create_app(simulation_mode=True)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_publisher] = lambda: Publisher()
    client = TestClient(app)
    payload = dict(action='jour_suivant', expected_state=end.current_state, control_id=next_id('control'))
    assert client.post('/api/v1/simulation/controls', json=payload).status_code == 202
    assert client.post('/api/v1/simulation/controls', json=payload).status_code == 202
    result = client.get('/api/v1/simulation').json()
    assert result['cycle'] == 2 and result['heure_virtuelle'] == 0
    assert result['current_state'] == end.current_state + 1
    assert client.get('/api/v1/plants/basilic/measurements').json()[0]['cycle'] == 2
    db.dispose()


def test_measurements_and_journal_have_distinct_server_limits(tmp_path):
    from greenmind.db.models import GreenhouseEventRow
    from greenmind.db.readings import list_events
    db = create_database_engine(tmp_path / 'limits.sqlite')
    engine = SimulationEngine(load_greenhouse_config(ROOT / 'config/greenhouse.yaml'),
                              load_weather(ROOT / 'data/fixtures/weather_greenhouse_day.csv'))
    for _ in range(105):
        save_message(db, telemetry_for_snapshot(engine.snapshot(), 'signal_presence')[0])
    simulation = engine.snapshot().simulation
    with Session(db) as session, session.begin():
        session.add_all(GreenhouseEventRow(event_id=next_id('event'), simulation=simulation,
            created_at='2026-07-10 00:00:00.00000', event_type='test', summary='test')
            for _ in range(105))
    assert len(recent_readings(db, simulation, 'basilic', limit=1000)) == 105
    assert len(list_events(db, simulation, limit=1000)) == 100
    db.dispose()
