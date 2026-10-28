"""Contrats, persistance et contrôles de la serre sur bases temporaires."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4
import pytest
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError
from greenmind.db.models import GreenhouseReading, SimulationRun, SimulationEventRow
from greenmind.db.session import create_database_engine
from greenmind.db.readings import latest_reading
from greenmind.ingestion.handler import ingest_telemetry
from greenmind.greenhouse_config import load_greenhouse_config
from greenmind.schemas import TelemetryV2, SimulationControl, parse_v2, telemetry_for_snapshot
from greenmind.simulator.controls import ControlProcessor
from greenmind.simulator.engine import SimulationEngine
from greenmind.simulator.weather import load_weather

ROOT = Path(__file__).resolve().parents[1]

@pytest.fixture
def simulation():
    return SimulationEngine(load_greenhouse_config(ROOT / 'config/greenhouse.yaml'),
                            load_weather(ROOT / 'data/fixtures/weather_greenhouse_day.csv'))

@pytest.fixture
def db(tmp_path):
    engine = create_database_engine(tmp_path / 'test.sqlite')
    yield engine
    engine.dispose()

def ingest(db, message):
    return ingest_telemetry(db, f'greenmind/v2/plants/{message.plant_id}/telemetry', message.model_dump_json())

def control(simulation, **changes):
    now = datetime.now(timezone.utc)
    values = dict(control_id=uuid4(), run_id=simulation.snapshot().run_id,
                  expected_revision=simulation.snapshot().state_revision, action='ADVANCE',
                  requested_at=now, expires_at=now + timedelta(seconds=30))
    return SimulationControl(**(values | changes))

def count(db, model):
    with Session(db) as session:
        return session.scalar(select(func.count()).select_from(model))

@pytest.mark.parametrize('field,value', [
    ('schema_version', 1), ('schema_version', True), ('plant_id', 'tomate_01'),
    ('run_id', 'incorrect'), ('event_id', 'incorrect'), ('simulated_tick', -1),
    ('simulated_tick', 25), ('state_revision', -1), ('soil_moisture_sim_pct', 101),
    ('air_humidity_pct', -1), ('air_temperature_c', float('nan')),
    ('paused', 'true'), ('completed', True), ('measurement_origin', 'inconnue'),
    ('observed_at', '2026-07-10T00:00:00'), ('unexpected', 42),
])
def test_bad_telemetry_is_rejected(simulation, db, field, value):
    message = telemetry_for_snapshot(simulation.snapshot(), 'initial')[0]
    data = message.model_dump(mode='json') | {field: value}
    with pytest.raises(ValueError):
        ingest_telemetry(db, 'greenmind/v2/plants/basilic_01/telemetry', json.dumps(data))
    assert count(db, GreenhouseReading) == count(db, SimulationRun) == 0

@pytest.mark.parametrize('field', ['schema_version', 'run_id', 'state_revision', 'simulated_at'])
def test_required_fields(simulation, field):
    data = telemetry_for_snapshot(simulation.snapshot(), 'initial')[0].model_dump(mode='json')
    del data[field]
    with pytest.raises(ValueError):
        parse_v2(TelemetryV2, json.dumps(data))

def test_three_beds_roundtrip_and_dedup(simulation, db):
    messages = telemetry_for_snapshot(simulation.snapshot(), 'initial')
    for message in messages:
        assert parse_v2(TelemetryV2, message.model_dump_json()) == message
        assert ingest(db, message)
        assert not ingest(db, message)
        row = latest_reading(db, str(message.run_id), message.plant_id)
        assert row.soil_moisture_sim_pct == message.soil_moisture_sim_pct
        assert row.received_at.endswith('Z') and len(row.received_at) == 27
    assert count(db, GreenhouseReading) == 3
    assert count(db, SimulationRun) == 1

def test_topic_mismatch_then_valid(simulation, db):
    message = telemetry_for_snapshot(simulation.snapshot(), 'initial')[0]
    for topic in ('greenmind/v1/plants/basilic_01/telemetry', 'greenmind/v2/plants/thym_01/telemetry'):
        with pytest.raises(ValueError):
            ingest_telemetry(db, topic, message.model_dump_json())
    with pytest.raises(ValueError):
        ingest_telemetry(db, 'greenmind/v2/plants/basilic_01/telemetry', b'{')
    assert ingest(db, message)

def test_late_state_and_other_run_do_not_replace_current(simulation, db):
    old = telemetry_for_snapshot(simulation.snapshot(), 'initial')[0]
    simulation.advance_one_hour()
    new = telemetry_for_snapshot(simulation.snapshot(), 'model')[0]
    assert ingest(db, new)
    assert ingest(db, old.model_copy(update={'emitted_at': new.emitted_at + timedelta(seconds=10)}))
    other = new.model_copy(update={'event_id': uuid4(), 'run_id': uuid4(), 'state_revision': 99})
    assert ingest(db, other)
    assert latest_reading(db, str(new.run_id), new.plant_id).event_id == str(new.event_id)

def test_heartbeat_new_id_same_state(simulation, db):
    for _ in range(2):
        for message in telemetry_for_snapshot(simulation.snapshot(), 'heartbeat'):
            ingest(db, message)
    assert count(db, GreenhouseReading) == 6
    assert simulation.snapshot().state_revision == 0

def test_persistence_after_reopen(simulation, tmp_path):
    path = tmp_path / 'persist.sqlite'
    message = telemetry_for_snapshot(simulation.snapshot(), 'initial')[0]
    db = create_database_engine(path)
    ingest(db, message)
    db.dispose()
    db = create_database_engine(path)
    try:
        assert latest_reading(db, str(message.run_id), message.plant_id).event_id == str(message.event_id)
    finally:
        db.dispose()

def test_sql_failure_rolls_back_run_creation(simulation, db):
    with db.begin() as connection:
        connection.exec_driver_sql('DROP TABLE sensor_readings')
    with pytest.raises(OperationalError):
        ingest(db, telemetry_for_snapshot(simulation.snapshot(), 'initial')[0])
    assert count(db, SimulationRun) == 0

def test_control_duplicate_same_event_and_single_effect(simulation, db):
    processor = ControlProcessor(simulation)
    request = control(simulation)
    first = processor.apply(request)
    duplicate = processor.apply(request)
    assert first == duplicate
    assert simulation.snapshot().simulated_tick == 1
    assert first.event.status == 'APPLIED'
    for response in (first, duplicate):
        for message in response.telemetry:
            ingest(db, message)
        ingest_telemetry(db, 'greenmind/v2/simulation/events', response.event.model_dump_json())
    assert count(db, GreenhouseReading) == 3
    assert count(db, SimulationEventRow) == 1

def test_control_id_collision_rejected_without_replacing_cache(simulation):
    processor = ControlProcessor(simulation)
    request = control(simulation)
    result = processor.apply(request)
    collision = processor.apply(request.model_copy(update={'action': 'PAUSE'}))
    assert collision.event.status == 'REJECTED'
    assert processor.apply(request) == result
    assert simulation.snapshot().simulated_tick == 1

@pytest.mark.parametrize('case', ['old_run', 'old_revision', 'expired', 'future'])
def test_invalid_control_rejected_without_effect(simulation, case):
    now = datetime.now(timezone.utc)
    changes = {}
    if case == 'old_run': changes['run_id'] = uuid4()
    if case == 'old_revision': changes['expected_revision'] = 5
    if case == 'expired': changes.update(requested_at=now-timedelta(seconds=60), expires_at=now-timedelta(seconds=30))
    if case == 'future': changes.update(requested_at=now+timedelta(seconds=10), expires_at=now+timedelta(seconds=30))
    before = simulation.snapshot()
    result = ControlProcessor(simulation).apply(control(simulation, **changes), now)
    assert result.event.status == 'REJECTED'
    assert not result.telemetry
    assert simulation.snapshot() == before

def test_override_and_running_refusal(simulation):
    processor = ControlProcessor(simulation)
    result = processor.apply(control(simulation, action='SET_SOIL_MOISTURE', plant_id='thym_01', value=18.0))
    assert result.event.status == 'APPLIED'
    assert [m.plant_id for m in result.telemetry if m.measurement_origin == 'manual_override'] == ['thym_01']
    processor.apply(control(simulation, action='RESUME'))
    assert processor.apply(control(simulation)).event.status == 'REJECTED'

@pytest.mark.parametrize('changes', [
    {'action': 'ADVANCE', 'plant_id': 'thym_01'},
    {'action': 'SET_SOIL_MOISTURE'},
    {'action': 'SET_SOIL_MOISTURE', 'plant_id': 'thym_01', 'value': 101},
    {'expires_at': datetime.now(timezone.utc)+timedelta(hours=1)},
])
def test_bad_control_arguments(simulation, changes):
    with pytest.raises(ValueError):
        control(simulation, **changes)


@pytest.mark.parametrize('kind', ['telemetry', 'simulation_event'])
def test_retained_messages_are_rejected_before_persistence(simulation, db, kind):
    if kind == 'telemetry':
        message = telemetry_for_snapshot(simulation.snapshot(), 'initial')[0]
        topic = f'greenmind/v2/plants/{message.plant_id}/telemetry'
    else:
        message = ControlProcessor(simulation).state_event()
        topic = 'greenmind/v2/simulation/events'
    with pytest.raises(ValueError, match='retained'):
        ingest_telemetry(db, topic, message.model_dump_json(), retained=True)
    assert count(db, SimulationRun) == 0
    assert count(db, GreenhouseReading) == count(db, SimulationEventRow) == 0
    assert ingest_telemetry(db, topic, message.model_dump_json())


@pytest.mark.parametrize('retained', [True, False])
def test_ingestion_callback_rejects_retained_and_acknowledges(simulation, tmp_path, monkeypatch, retained):
    import importlib
    import signal
    from types import SimpleNamespace
    service = importlib.import_module('greenmind.ingestion.main')
    message = telemetry_for_snapshot(simulation.snapshot(), 'initial')[0]
    handlers = {}
    acknowledgements = []
    def register(signum, handler):
        previous = handlers.get(signum, signal.SIG_DFL)
        handlers[signum] = handler
        return previous
    class FakeClient:
        def __init__(self, *args, **kwargs): pass
        def reconnect_delay_set(self, **kwargs): pass
        def connect_async(self, *args, **kwargs): pass
        def subscribe(self, *args, **kwargs): return (0, 1)
        def loop_start(self):
            self.on_connect(self, None, None, SimpleNamespace(is_failure=False), None)
            self.on_subscribe(self, None, 1, [1, 1], None)
            self.on_message(self, None, SimpleNamespace(
                topic=f'greenmind/v2/plants/{message.plant_id}/telemetry',
                payload=message.model_dump_json().encode(), retain=retained, mid=7, qos=1,
            ))
            handlers[signal.SIGTERM](signal.SIGTERM, None)
            return 0
        def ack(self, mid, qos):
            acknowledgements.append((mid, qos))
            return 0
        def disconnect(self): pass
        def loop_stop(self): pass
    path = tmp_path / 'callback.sqlite'
    monkeypatch.setenv('GREENMIND_DATABASE_PATH', str(path))
    monkeypatch.setattr(service.mqtt, 'Client', FakeClient)
    monkeypatch.setattr(service.signal, 'signal', register)
    assert service.main() == 0
    db = create_database_engine(path)
    try:
        assert count(db, GreenhouseReading) == (0 if retained else 1)
        assert acknowledgements == [(7, 1)]
    finally:
        db.dispose()


def test_control_table_is_added_to_existing_v2_without_data_loss(simulation, tmp_path):
    from sqlalchemy import MetaData, inspect
    from greenmind.db.models import Base
    from greenmind.db.readings import reserve_control, save_message
    metadata = MetaData()
    for table in Base.metadata.sorted_tables:
        if table.name != 'simulation_controls':
            table.to_metadata(metadata)
    path = tmp_path / 'existing_v2.sqlite'
    original = create_database_engine(path, metadata=metadata)
    message = telemetry_for_snapshot(simulation.snapshot(), 'initial')[0]
    save_message(original, message)
    assert 'simulation_controls' not in inspect(original).get_table_names()
    original.dispose()
    upgraded = create_database_engine(path)
    try:
        assert 'simulation_controls' in inspect(upgraded).get_table_names()
        assert latest_reading(upgraded, message.run_id, message.plant_id).event_id == str(message.event_id)
        request = control(simulation)
        assert reserve_control(upgraded, request) == request
    finally:
        upgraded.dispose()
