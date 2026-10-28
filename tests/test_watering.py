"""B5 : effet unique, confirmation, isolement, refus et incertitude."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from greenmind.api.app import create_app
from greenmind.api.dependencies import get_config, get_db, get_publisher
from greenmind.db import watering
from greenmind.db.models import WateringCommandRow, WateringEventRow
from greenmind.db.readings import save_message, active_alert, list_events
from greenmind.db.session import create_database_engine
from greenmind.greenhouse_config import load_greenhouse_config
from greenmind.ingestion.handler import ingest_telemetry
from greenmind.schemas import WateringCommand, telemetry_for_snapshot
from greenmind.simulator.engine import SimulationEngine
from greenmind.simulator.watering import WateringProcessor
from greenmind.simulator.weather import load_weather

ROOT = Path(__file__).resolve().parents[1]
LOW = {'basilic_01': 20.0, 'thym_01': 10.0, 'romarin_01': 15.0}


@pytest.fixture
def system(tmp_path, monkeypatch):
    config = load_greenhouse_config(ROOT / 'config/greenhouse.yaml')
    engine = SimulationEngine(config, load_weather(ROOT / 'data/fixtures/weather_greenhouse_day.csv'))
    db = create_database_engine(tmp_path / 'watering.sqlite')
    for plant, moisture in LOW.items():
        engine.set_soil_moisture(plant, moisture)
    for m in telemetry_for_snapshot(engine.snapshot(), 'heartbeat'):
        save_message(db, m)
    now = [datetime.now(timezone.utc)]
    monkeypatch.setattr(watering, 'utcnow', lambda: now[0])
    class Publisher:
        def __init__(self): self.published = []
        def publish_watering(self, plant, payload):
            self.published.append(WateringCommand.model_validate_json(payload))
        def publish_control(self, payload): pass
    publisher = Publisher()
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_config] = lambda: config
    app.dependency_overrides[get_publisher] = lambda: publisher
    clock = [100.0]
    processor = WateringProcessor(engine, config, clock=lambda: clock[0])
    with TestClient(app) as client:
        yield SimpleNamespace(db=db, config=config, engine=engine, processor=processor,
                              publisher=publisher, client=client, now=now, clock=clock)
    db.dispose()


def propose(s, plant='thym_01', **payload):
    return s.client.post(f'/api/v1/plants/{plant}/watering-proposals', json=payload)


def confirm(s, proposal, plant='thym_01', command_id=None):
    return s.client.post(f'/api/v1/plants/{plant}/watering-commands', json={
        'proposal_id': proposal['proposal_id'], 'command_id': command_id or str(uuid4()),
    })


def track(s, command_id):
    return s.client.get(f'/api/v1/watering-commands/{command_id}').json()


def apply(s, command=None, telemetry=True):
    command = command or s.publisher.published[-1]
    result = s.processor.apply(command, now=command.requested_at)
    save_message(s.db, result.event)
    if telemetry:
        for m in result.telemetry:
            save_message(s.db, m)
    return result


@pytest.mark.parametrize('plant', LOW)
def test_complete_watering_cycle_is_targeted_and_idempotent(system, plant):
    s = system
    before = s.engine.snapshot()
    proposal_id = str(uuid4())
    response = propose(s, plant, proposal_id=proposal_id)
    assert response.status_code == 201
    proposal = response.json()
    assert proposal == propose(s, plant, proposal_id=proposal_id).json()
    assert s.engine.snapshot() == before and not s.publisher.published
    command_id = str(uuid4())
    accepted = confirm(s, proposal, plant, command_id)
    assert accepted.status_code == 202 and accepted.json()['status'] == 'SENT'
    assert confirm(s, proposal, plant, command_id).status_code == 202
    assert len(s.publisher.published) == 1
    result = apply(s, telemetry=False)
    state = s.engine.snapshot()
    assert result.event.status == 'APPLIED'
    assert state.simulated_at == before.simulated_at and state.simulated_tick == before.simulated_tick
    assert state.state_revision == before.state_revision + 1
    assert state.soil[plant] == pytest.approx(proposal['soil_moisture_after_pct'])
    assert all(state.soil[p] == before.soil[p] for p in LOW if p != plant)
    assert track(s, command_id)['status'] == 'EXECUTED'
    assert track(s, command_id)['measurement_pending']
    assert s.client.post('/api/v1/simulation/controls', json={'action': 'ADVANCE', 'expected_revision': state.state_revision}).status_code == 409
    # Même le retour MQTT de l'ACK et des mesures est idempotent.
    assert not save_message(s.db, result.event)
    assert s.processor.apply(s.publisher.published[-1]) == result
    for m in result.telemetry:
        assert save_message(s.db, m)
        assert not save_message(s.db, m)
    assert not track(s, command_id)['measurement_pending']
    assert active_alert(s.db, state.run_id, plant) is None
    assert confirm(s, proposal, plant, command_id).status_code == 202
    assert len(s.publisher.published) == 1
    events = list_events(s.db, state.run_id, plant)
    assert sum(e.event_type == 'WATERING_EXECUTED' for e in events) == 1
    assert sum(e.event_type == 'ALERT_CLOSED' for e in events) == 1


def test_duration_cap_is_visible_and_does_not_claim_target_reached(system):
    s = system
    s.engine.set_soil_moisture('basilic_01', 0.0)
    for m in telemetry_for_snapshot(s.engine.snapshot(), 'heartbeat'):
        save_message(s.db, m)
    s.now[0] = datetime.now(timezone.utc)
    proposal = propose(s, 'basilic_01').json()
    assert proposal['capped'] and proposal['duration_sim_s'] == 10
    assert proposal['soil_moisture_after_pct'] == 30
    assert 'ne sera pas atteinte' in proposal['reason']
    assert confirm(s, proposal, 'basilic_01').status_code == 202
    assert apply(s).event.soil_moisture_after_pct == 30
    assert active_alert(s.db, s.engine.snapshot().run_id, 'basilic_01') is not None


@pytest.mark.parametrize('case,expected', [('expired', 409), ('changed', 409), ('stale', 503), ('old_run', 409)])
def test_confirmation_revalidates_proposal(system, case, expected):
    s = system
    proposal = propose(s).json()
    if case == 'expired':
        s.now[0] += timedelta(seconds=61)
    elif case == 'stale':
        s.now[0] += timedelta(seconds=11)
    elif case == 'changed':
        s.engine.set_soil_moisture('thym_01', 11.0)
        for m in telemetry_for_snapshot(s.engine.snapshot(), 'heartbeat'):
            save_message(s.db, m)
        s.now[0] = datetime.now(timezone.utc)
    else:
        from dataclasses import replace
        new_state = replace(s.engine.snapshot(), run_id=uuid4())
        for m in telemetry_for_snapshot(new_state, 'heartbeat'):
            save_message(s.db, m)
        s.now[0] = datetime.now(timezone.utc)
    assert confirm(s, proposal).status_code == expected
    assert not s.publisher.published


def test_heartbeat_does_not_invalidate_proposal(system):
    s = system
    proposal = propose(s).json()
    for m in telemetry_for_snapshot(s.engine.snapshot(), 'heartbeat'):
        save_message(s.db, m)
    s.now[0] = datetime.now(timezone.utc)
    assert confirm(s, proposal).status_code == 202


def test_only_one_pending_watering_in_greenhouse(system):
    s = system
    proposals = {p: propose(s, p).json() for p in LOW}
    assert confirm(s, proposals['thym_01']).status_code == 202
    assert confirm(s, proposals['basilic_01'], 'basilic_01').status_code == 409
    assert propose(s, 'romarin_01').status_code == 409
    assert s.client.post('/api/v1/simulation/controls', json={'action': 'ADVANCE', 'expected_revision': 3}).status_code == 409
    assert len(s.publisher.published) == 1


@pytest.mark.parametrize('same_key', [True, False])
def test_concurrent_confirmations_have_one_publication(system, same_key):
    s = system
    proposal = propose(s).json()
    key = str(uuid4())
    with ThreadPoolExecutor(max_workers=4) as executor:
        responses = list(executor.map(lambda _: confirm(s, proposal, command_id=key if same_key else str(uuid4())), range(4)))
    statuses = [r.status_code for r in responses]
    assert statuses == [202] * 4 if same_key else sorted(statuses) == [202, 409, 409, 409]
    assert len(s.publisher.published) == 1


def test_timeout_locks_mutations_and_late_ack_resolves_once(system):
    s = system
    accepted = confirm(s, propose(s).json()).json()
    result = s.processor.apply(s.publisher.published[-1], now=s.now[0])
    s.now[0] += timedelta(seconds=11)
    assert track(s, accepted['command_id'])['status'] == 'TIMED_OUT'
    assert propose(s, 'basilic_01').status_code == 409
    assert confirm(s, {'proposal_id': accepted['proposal_id']}, command_id=accepted['command_id']).json()['status'] == 'TIMED_OUT'
    assert len(s.publisher.published) == 1
    save_message(s.db, result.event)
    assert track(s, accepted['command_id'])['measurement_pending']
    for m in result.telemetry:
        save_message(s.db, m)
    assert not track(s, accepted['command_id'])['measurement_pending']
    entries = list_events(s.db, s.engine.snapshot().run_id)
    assert sum(e.event_type == 'WATERING_TIMED_OUT' for e in entries) == 1
    executed = next(e for e in entries if e.event_type == 'WATERING_EXECUTED')
    assert '"late_ack": true' in executed.details_json


def test_publish_failure_is_uncertain_and_never_resent(system, monkeypatch):
    s = system
    proposal = propose(s).json()
    key = str(uuid4())
    def fail(*args): raise HTTPException(status_code=503, detail='Broker indisponible.')
    monkeypatch.setattr(s.publisher, 'publish_watering', fail)
    response = confirm(s, proposal, command_id=key)
    assert response.status_code == 503 and response.json()['detail']['command_id'] == key
    assert track(s, key)['status'] == 'TIMED_OUT'
    assert confirm(s, proposal, command_id=key).status_code == 202
    assert propose(s, 'romarin_01').status_code == 409


def test_cooldown_is_per_bed_and_enforced_twice(system):
    s = system
    assert confirm(s, propose(s).json()).status_code == 202
    apply(s)
    s.engine.set_soil_moisture('thym_01', 10.0)
    for m in telemetry_for_snapshot(s.engine.snapshot(), 'heartbeat'):
        save_message(s.db, m)
    s.now[0] = datetime.now(timezone.utc)
    assert propose(s).status_code == 409
    assert propose(s, 'basilic_01').status_code == 201
    # Le simulateur protège aussi un émetteur MQTT qui contournerait l'API.
    original = s.publisher.published[-1]
    retry = original.model_copy(update={'command_id': uuid4(), 'expected_revision': s.engine.snapshot().state_revision})
    assert s.processor.apply(retry, now=original.requested_at).event.status == 'REJECTED'
    s.now[0] += timedelta(seconds=61)
    s.clock[0] += 61
    for m in telemetry_for_snapshot(s.engine.snapshot(), 'heartbeat'):
        save_message(s.db, m.model_copy(update={'emitted_at': s.now[0]}))
    assert confirm(s, propose(s).json()).status_code == 202
    assert apply(s).event.status == 'APPLIED'


@pytest.mark.parametrize('case', ['expired', 'old_run', 'old_revision', 'bad_duration', 'collision'])
def test_simulator_refuses_unsafe_commands_without_effect(system, case):
    s = system
    confirm(s, propose(s).json())
    command = s.publisher.published[-1]
    if case == 'collision':
        result = s.processor.apply(command, now=s.now[0])
        command = command.model_copy(update={'duration_sim_s': 1.0})
    elif case == 'expired':
        s.now[0] += timedelta(seconds=11)
    elif case == 'old_run':
        command = command.model_copy(update={'run_id': uuid4()})
    elif case == 'old_revision':
        command = command.model_copy(update={'expected_revision': 0})
    else:
        command = command.model_copy(update={'duration_sim_s': 0.5})
    before = s.engine.snapshot()
    result = s.processor.apply(command, now=s.now[0])
    assert result.event.status == 'REJECTED' and not result.telemetry
    assert s.engine.snapshot() == before


def test_confirmation_requires_proposal_and_checks_key_content(system):
    s = system
    assert confirm(s, {'proposal_id': str(uuid4())}).status_code == 404
    proposal = propose(s).json()
    assert confirm(s, proposal, 'basilic_01').status_code == 404
    assert s.client.post('/api/v1/plants/thym_01/watering-commands', json={'proposal_id': proposal['proposal_id'], 'duration_sim_s': 10}).status_code == 422
    key = str(uuid4())
    assert confirm(s, proposal, command_id=key).status_code == 202
    assert confirm(s, {'proposal_id': str(uuid4())}, command_id=key).status_code == 409
    assert s.client.get(f'/api/v1/watering-commands/{uuid4()}').status_code == 404
    assert propose(s, 'inconnu').status_code == 404


def test_ingestion_validates_watering_topic_and_retained(system):
    s = system
    confirm(s, propose(s).json())
    result = s.processor.apply(s.publisher.published[-1], now=s.now[0])
    for topic, retained in [('greenmind/v2/plants/basilic_01/events', False), ('greenmind/v2/plants/thym_01/events', True)]:
        with pytest.raises(ValueError):
            ingest_telemetry(s.db, topic, result.event.model_dump_json(), retained=retained)
    assert ingest_telemetry(s.db, 'greenmind/v2/plants/thym_01/events', result.event.model_dump_json())
    assert track(s, str(result.event.command_id))['status'] == 'EXECUTED'


def test_ack_failure_rolls_back_command_status_and_event(system):
    s = system
    confirm(s, propose(s).json())
    result = s.processor.apply(s.publisher.published[-1], now=s.now[0])
    bad = result.event.model_copy(update={'resulting_revision': 99})
    with pytest.raises(ValueError, match='incohérent'):
        save_message(s.db, bad)
    with Session(s.db) as session:
        assert session.scalar(select(func.count()).select_from(WateringEventRow)) == 0
    assert track(s, str(result.event.command_id))['status'] == 'SENT'
    save_message(s.db, result.event)
    assert track(s, str(result.event.command_id))['status'] == 'EXECUTED'


@pytest.mark.parametrize('plant', LOW)
@pytest.mark.parametrize('above', [0.0, 1.0])
def test_no_proposal_at_or_above_low_threshold(system, plant, above):
    s = system
    profile = s.config.get_plant(plant)
    s.engine.set_soil_moisture(plant, profile.low_threshold_sim_pct + above)
    for m in telemetry_for_snapshot(s.engine.snapshot(), 'heartbeat'):
        save_message(s.db, m)
    s.now[0] = datetime.now(timezone.utc)
    assert propose(s, plant).status_code == 409
    assert not s.publisher.published


def test_api_restart_preserves_uncertain_operation_without_republication(system):
    s = system
    accepted = confirm(s, propose(s).json()).json()
    s.db.dispose()
    reopened = create_database_engine(Path(s.db.url.database))
    app = create_app()
    app.dependency_overrides[get_db] = lambda: reopened
    app.dependency_overrides[get_config] = lambda: s.config
    app.dependency_overrides[get_publisher] = lambda: s.publisher
    s.now[0] += timedelta(seconds=11)
    try:
        with TestClient(app) as client:
            response = client.get(f"/api/v1/watering-commands/{accepted['command_id']}")
            assert response.json()['status'] == 'TIMED_OUT'
            assert client.post('/api/v1/plants/basilic_01/watering-proposals', json={}).status_code == 409
            assert len(s.publisher.published) == 1
    finally:
        reopened.dispose()


def test_failed_confirmation_transaction_does_not_consume_proposal(system, monkeypatch):
    s = system
    proposal = propose(s).json()
    def broken_journal(*args, **kwargs):
        raise RuntimeError('Journal indisponible')
    with monkeypatch.context() as patch:
        patch.setattr(watering, 'journal', broken_journal)
        with pytest.raises(RuntimeError, match='Journal indisponible'):
            watering.confirm_proposal(s.db, s.config, 'thym_01', proposal['proposal_id'], uuid4())
    with Session(s.db) as session:
        assert session.scalar(select(func.count()).select_from(WateringCommandRow)) == 0
    assert confirm(s, proposal).status_code == 202


@pytest.mark.parametrize('field,value', [
    ('schema_version', 1), ('duration_sim_s', 0), ('duration_sim_s', 11),
    ('actuator_id', 'arroseur_basilic'), ('expected_revision', -1),
    ('requested_at', '2026-10-28T00:00:00'), ('unexpected', True),
])
def test_invalid_watering_wire_contract_is_rejected(system, field, value):
    import json
    from greenmind.schemas import parse_v2
    s = system
    confirm(s, propose(s).json())
    data = s.publisher.published[-1].model_dump(mode='json') | {field: value}
    with pytest.raises(ValueError):
        parse_v2(WateringCommand, json.dumps(data))


def test_watering_dates_are_normalized_before_deduplication(system):
    import json
    from greenmind.schemas import parse_v2
    s = system
    confirm(s, propose(s).json())
    command = s.publisher.published[-1]
    data = command.model_dump(mode='json')
    offset = timezone(timedelta(hours=2))
    for key in ('requested_at', 'expires_at'):
        data[key] = getattr(command, key).astimezone(offset).isoformat()
    normalized = parse_v2(WateringCommand, json.dumps(data))
    assert normalized.model_dump_json() == command.model_dump_json()
