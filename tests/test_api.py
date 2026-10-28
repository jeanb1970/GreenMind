"""Tests d'intégration de l'API REST FastAPI (/api/v1)."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from greenmind.api.app import create_app
from greenmind.api.dependencies import get_config, get_db, get_publisher
from greenmind.db.models import SimulationEventRow
from greenmind.db.readings import save_message
from greenmind.db.session import create_database_engine
from greenmind.greenhouse_config import load_greenhouse_config
from greenmind.schemas import TelemetryV2

ROOT = Path(__file__).resolve().parents[1]


class FakeMqttPublisher:
    def __init__(self):
        self.published = []

    def publish_control(self, payload_json: str) -> None:
        self.published.append(payload_json)


@pytest.fixture
def config():
    return load_greenhouse_config(ROOT / "config/greenhouse.yaml")


@pytest.fixture
def db(tmp_path):
    engine = create_database_engine(tmp_path / "test_api.sqlite")
    yield engine
    engine.dispose()


@pytest.fixture
def fake_publisher():
    return FakeMqttPublisher()


@pytest.fixture
def client(db, config, fake_publisher):
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_config] = lambda: config
    app.dependency_overrides[get_publisher] = lambda: fake_publisher
    return TestClient(app)


def seed_telemetry(db, config, run_id, moisture=48.0, tick=1, revision=1):
    now = datetime(2026, 7, 10, 0, 0, 0, tzinfo=timezone.utc)
    offset = timedelta(hours=1 if tick else 0)
    for plant_id in ("basilic_01", "thym_01", "romarin_01"):
        val = 18.0 if plant_id == "thym_01" else moisture
        m = TelemetryV2(
            event_id=uuid4(),
            run_id=run_id,
            plant_id=plant_id,
            observed_at=now,
            simulated_at=now + offset,
            emitted_at=now,
            simulated_tick=tick,
            state_revision=revision,
            paused=True,
            completed=False,
            air_temperature_c=22.0,
            air_humidity_pct=60.0,
            soil_moisture_sim_pct=val,
            pump_active=False,
            provenance="synthetic_weather_plus_synthetic_soil",
            measurement_origin="model",
        )
        save_message(db, m, config=config)


def test_health_endpoint(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["database_connected"] is True
    assert data["demo_mode"] is True
    assert data["status"] in ("ok", "degraded")


def test_get_plants_empty_and_seeded(client, db, config):
    # Base vide
    response = client.get("/api/v1/plants")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3
    plant_ids = [p["plant_id"] for p in data]
    assert plant_ids == ["basilic_01", "thym_01", "romarin_01"]
    assert all(p["soil_moisture_sim_pct"] is None for p in data)

    # Base alimentée
    run_id = uuid4()
    seed_telemetry(db, config, run_id)
    response = client.get("/api/v1/plants")
    assert response.status_code == 200
    data = response.json()
    thym = next(p for p in data if p["plant_id"] == "thym_01")
    assert thym["soil_moisture_sim_pct"] == 18.0
    # Thym à 18 % < 20 % -> alerte active
    assert thym["has_active_alert"] is True
    assert thym["active_alert"] is not None
    assert thym["active_alert"]["status"] == "OPEN"

    basilic = next(p for p in data if p["plant_id"] == "basilic_01")
    assert basilic["soil_moisture_sim_pct"] == 48.0
    assert basilic["has_active_alert"] is False


def test_get_plant_detail_and_not_found(client, db, config):
    run_id = uuid4()
    seed_telemetry(db, config, run_id)

    # Bac valide
    response = client.get("/api/v1/plants/basilic_01")
    assert response.status_code == 200
    data = response.json()
    assert data["plant_id"] == "basilic_01"
    assert data["display_name"] == "Basilic"
    assert data["low_threshold_sim_pct"] == 35.0
    assert data["rearm_threshold_sim_pct"] == 40.0
    assert data["actuator_id"] == "arroseur_basilic"

    # Bac inconnu -> 404
    response_404 = client.get("/api/v1/plants/tomate_01")
    assert response_404.status_code == 404
    assert "inconnu" in response_404.json()["detail"].lower()


def test_get_measurements_limit(client, db, config):
    run_id = uuid4()
    seed_telemetry(db, config, run_id, tick=1, revision=1)
    seed_telemetry(db, config, run_id, tick=2, revision=2)

    response = client.get("/api/v1/plants/basilic_01/measurements?limit=1")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["simulated_tick"] == 2

    # Bac inconnu
    assert client.get("/api/v1/plants/inconnu/measurements").status_code == 404


def test_get_events_and_filtering(client, db, config):
    run_id = uuid4()
    seed_telemetry(db, config, run_id)  # Ouvre alerte sur thym_01

    response = client.get("/api/v1/events")
    assert response.status_code == 200
    events = response.json()
    assert len(events) >= 1
    assert any(e["event_type"] == "ALERT_OPENED" for e in events)

    # Filtre par bac existant
    response_thym = client.get("/api/v1/events?plant_id=thym_01")
    assert response_thym.status_code == 200
    assert all(e["plant_id"] == "thym_01" for e in response_thym.json())

    # Filtre par bac inconnu -> 404
    assert client.get("/api/v1/events?plant_id=inconnu").status_code == 404


def test_simulation_state(client, db, config):
    run_id = uuid4()
    seed_telemetry(db, config, run_id, tick=1, revision=1)

    response = client.get("/api/v1/simulation")
    assert response.status_code == 200
    data = response.json()
    assert data["run_id"] == str(run_id)
    assert data["simulated_tick"] == 1
    assert data["state_revision"] == 1
    assert data["paused"] is True


def test_post_simulation_control_accepted(client, db, config, fake_publisher):
    run_id = uuid4()
    seed_telemetry(db, config, run_id, tick=1, revision=1)

    payload = {
        "action": "ADVANCE",
        "expected_revision": 1,
    }
    response = client.post("/api/v1/simulation/controls", json=payload)
    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "PENDING"
    assert data["action"] == "ADVANCE"
    assert len(fake_publisher.published) == 1
    assert "ADVANCE" in fake_publisher.published[0]


def test_post_simulation_control_revision_conflict(client, db, config):
    run_id = uuid4()
    seed_telemetry(db, config, run_id, tick=1, revision=2)

    # Demande avec expected_revision obsolète (1 != 2)
    payload = {
        "action": "ADVANCE",
        "expected_revision": 1,
    }
    response = client.post("/api/v1/simulation/controls", json=payload)
    assert response.status_code == 409
    assert "conflit" in response.json()["detail"].lower()


def test_post_simulation_control_validation_error(client, db, config):
    run_id = uuid4()
    seed_telemetry(db, config, run_id, tick=1, revision=1)

    # SET_SOIL_MOISTURE sans bac ni valeur -> 422
    payload = {
        "action": "SET_SOIL_MOISTURE",
        "expected_revision": 1,
    }
    response = client.post("/api/v1/simulation/controls", json=payload)
    assert response.status_code == 422


def test_get_control_status(client, db):
    control_id = uuid4()
    # Statut non encore acquitté
    res_pending = client.get(f"/api/v1/simulation/controls/{control_id}")
    assert res_pending.status_code == 200
    assert res_pending.json()["status"] == "PENDING"

    # Insertion d'un acquittement via save_message
    from greenmind.schemas import SimulationEvent
    now = datetime(2026, 7, 10, 0, 0, 0, tzinfo=timezone.utc)
    run_id = uuid4()
    evt = SimulationEvent(
        event_id=uuid4(),
        run_id=run_id,
        control_id=control_id,
        status="APPLIED",
        state_revision=2,
        simulated_tick=2,
        simulated_at=now,
        emitted_at=now,
        paused=True,
        completed=False,
        reason="Avance de +1 heure appliquée.",
    )
    save_message(db, evt)

    res_applied = client.get(f"/api/v1/simulation/controls/{control_id}")
    assert res_applied.status_code == 200
    data = res_applied.json()
    assert data["status"] == "APPLIED"
    assert data["state_revision"] == 2
    assert "Avance" in data["reason"]


def test_control_retry_keeps_exact_wire_payload_after_api_restart(client, db, config, fake_publisher):
    from greenmind.schemas import SimulationControl
    from greenmind.simulator.controls import ControlProcessor
    from greenmind.simulator.engine import SimulationEngine
    from greenmind.simulator.weather import load_weather
    engine = SimulationEngine(config, load_weather(ROOT / 'data/fixtures/weather_greenhouse_day.csv'))
    processor = ControlProcessor(engine)
    run_id = engine.snapshot().run_id
    seed_telemetry(db, config, run_id, tick=0, revision=0)
    payload = {'action': 'ADVANCE', 'expected_revision': 0, 'control_id': str(uuid4())}
    assert client.post('/api/v1/simulation/controls', json=payload).status_code == 202
    # Nouvelle app et nouvelles connexions : la clé doit survivre au redémarrage.
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_publisher] = lambda: fake_publisher
    restarted = TestClient(app)
    assert restarted.post('/api/v1/simulation/controls', json=payload).status_code == 202
    assert fake_publisher.published[0] == fake_publisher.published[1]
    commands = [SimulationControl.model_validate_json(p) for p in fake_publisher.published]
    result = processor.apply(commands[0])
    assert processor.apply(commands[1]) == result
    assert engine.snapshot().simulated_tick == 1
    for telemetry in result.telemetry:
        save_message(db, telemetry, config=config)
    save_message(db, result.event)
    # Après acquittement et changement de révision, le rejeu reste accepté.
    assert restarted.post('/api/v1/simulation/controls', json=payload).status_code == 202
    assert len(fake_publisher.published) == 2
    assert restarted.get(f"/api/v1/simulation/controls/{payload['control_id']}").json()['status'] == 'APPLIED'
    # La même clé avec une intention différente doit être refusée.
    assert restarted.post('/api/v1/simulation/controls', json=payload | {'action': 'PAUSE'}).status_code == 409
    assert len(fake_publisher.published) == 2


def test_control_retry_after_publish_failure(client, db, config, fake_publisher, monkeypatch):
    from fastapi import HTTPException
    seed_telemetry(db, config, uuid4())
    payload = {'action': 'ADVANCE', 'expected_revision': 1, 'control_id': str(uuid4())}
    attempted = []
    def fail_publish(message):
        attempted.append(message)
        raise HTTPException(status_code=503, detail='Broker indisponible.')
    with monkeypatch.context() as patch:
        patch.setattr(fake_publisher, 'publish_control', fail_publish)
        assert client.post('/api/v1/simulation/controls', json=payload).status_code == 503
    assert client.post('/api/v1/simulation/controls', json=payload).status_code == 202
    assert fake_publisher.published == attempted


def test_concurrent_control_retries_share_one_payload(client, db, config, fake_publisher):
    from concurrent.futures import ThreadPoolExecutor
    seed_telemetry(db, config, uuid4())
    payload = {'action': 'ADVANCE', 'expected_revision': 1, 'control_id': str(uuid4())}
    with ThreadPoolExecutor(max_workers=4) as executor:
        responses = list(executor.map(lambda _: client.post('/api/v1/simulation/controls', json=payload), range(4)))
    assert all(r.status_code == 202 for r in responses)
    assert len(set(fake_publisher.published)) == 1


def test_api_database_path_matches_ingestion(tmp_path, monkeypatch):
    import greenmind.api.dependencies as dependencies
    path = tmp_path / 'configured.sqlite'
    monkeypatch.setenv('GREENMIND_DATABASE_PATH', str(path))
    monkeypatch.setattr(dependencies, '_GLOBAL_ENGINE', None)
    engine = dependencies.get_db()
    try:
        assert Path(engine.url.database) == path
    finally:
        engine.dispose()


def test_revision_conflict_does_not_reserve_control_id(client, db, config, fake_publisher):
    seed_telemetry(db, config, uuid4(), revision=2)
    payload = {'action': 'ADVANCE', 'expected_revision': 1, 'control_id': str(uuid4())}
    assert client.post('/api/v1/simulation/controls', json=payload).status_code == 409
    assert fake_publisher.published == []
    assert client.post('/api/v1/simulation/controls', json=payload | {'expected_revision': 2}).status_code == 202
    assert len(fake_publisher.published) == 1
