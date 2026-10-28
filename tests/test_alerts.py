"""Tests de persistance atomique des alertes et du journal d'événements."""
from greenmind.identifiers import next_id, next_simulation

from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from greenmind.db.models import AlertRow, GreenhouseEventRow, GreenhouseReading
from greenmind.db.readings import (
    active_alert,
    list_alerts,
    list_events,
    recent_readings,
    save_message,
)
from greenmind.db.session import create_database_engine
from greenmind.greenhouse_config import load_greenhouse_config
from greenmind.schemas import TelemetryV3

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def config():
    return load_greenhouse_config(ROOT / "config/greenhouse.yaml")


@pytest.fixture
def db(tmp_path):
    engine = create_database_engine(tmp_path / "test_alerts.sqlite")
    yield engine
    engine.dispose()


def make_telemetry(
    simulation,
    plant_id="basilic",
    moisture=50.0,
    tick=1,
    revision=1,
    origin="calcul_horaire",
):
    now = datetime(2026, 7, 10, 0, 0, 0, tzinfo=timezone.utc)
    offset = timedelta(hours=1 if tick else 0)
    return TelemetryV3(
        event_id=next_id("event"),
        simulation=simulation,
        plant_id=plant_id,
        observed_at=now,
        simulated_at=now + offset,
        emitted_at=now,
        heure_virtuelle=tick,
        current_state=revision,
        paused=False,
        day_complete=False,
        air_temperature_c=22.0,
        air_humidity_pct=60.0,
        soil_moisture_pct=moisture,
        arroseur_active=False,
        provenance="meteo_simulee",
        measurement_origin=origin,
    )


def test_alert_opens_when_below_low_threshold(db, config):
    simulation = next_simulation()
    # Basilic : seuil bas = 35 %, réarmement = 40 %
    m1 = make_telemetry(simulation, "basilic", moisture=50.0, tick=1, revision=1)
    save_message(db, m1, config=config)
    assert active_alert(db, simulation, "basilic") is None
    assert len(list_alerts(db, simulation, "basilic")) == 0

    # Baisse sous le seuil bas
    m2 = make_telemetry(simulation, "basilic", moisture=34.0, tick=2, revision=2)
    save_message(db, m2, config=config)

    alert = active_alert(db, simulation, "basilic")
    assert alert is not None
    assert alert.status == "ouverte"
    assert alert.moist_trigger_pct == 34.0
    assert alert.opening_event_id == str(m2.event_id)
    assert alert.closed_at is None

    events = list_events(db, simulation, "basilic")
    opened_events = [e for e in events if e.event_type == "alerte_ouverte"]
    assert len(opened_events) == 1
    assert "Basilic" in opened_events[0].summary
    assert "34.0" in opened_events[0].summary


def test_alert_remains_open_between_low_and_rearm_thresholds(db, config):
    simulation = next_simulation()
    # Déclenchement à 32 %
    save_message(db, make_telemetry(simulation, "basilic", moisture=32.0, tick=1, revision=1), config=config)
    initial_alert = active_alert(db, simulation, "basilic")
    assert initial_alert is not None

    # Remontée partielle à 38 % (entre 35 % et 40 %)
    save_message(db, make_telemetry(simulation, "basilic", moisture=38.0, tick=2, revision=2), config=config)
    current_alert = active_alert(db, simulation, "basilic")
    assert current_alert is not None
    assert current_alert.alert_id == initial_alert.alert_id
    assert current_alert.status == "ouverte"
    assert len(list_alerts(db, simulation, "basilic")) == 1


def test_alert_closes_when_exceeding_rearm_threshold(db, config):
    simulation = next_simulation()
    save_message(db, make_telemetry(simulation, "basilic", moisture=30.0, tick=1, revision=1), config=config)
    assert active_alert(db, simulation, "basilic") is not None

    # Dépassement du réarmement (41 % > 40 %)
    m_rearm = make_telemetry(simulation, "basilic", moisture=41.0, tick=2, revision=2)
    save_message(db, m_rearm, config=config)

    assert active_alert(db, simulation, "basilic") is None
    all_alerts = list_alerts(db, simulation, "basilic")
    assert len(all_alerts) == 1
    closed = all_alerts[0]
    assert closed.status == "clôturée"
    assert closed.closed_at is not None
    assert closed.closing_event_id == str(m_rearm.event_id)
    assert closed.moist_resolved_pct == 41.0

    events = list_events(db, simulation, "basilic")
    closed_events = [e for e in events if e.event_type == "alerte_clôturée"]
    assert len(closed_events) == 1
    assert "levée" in closed_events[0].summary.lower()


def test_alert_can_reopen_on_new_drop(db, config):
    simulation = next_simulation()
    # Cycle 1 : ouverture puis fermeture
    save_message(db, make_telemetry(simulation, "basilic", moisture=32.0, tick=1, revision=1), config=config)
    save_message(db, make_telemetry(simulation, "basilic", moisture=42.0, tick=2, revision=2), config=config)
    assert active_alert(db, simulation, "basilic") is None

    # Cycle 2 : nouvelle ouverture
    save_message(db, make_telemetry(simulation, "basilic", moisture=31.0, tick=3, revision=3), config=config)
    current = active_alert(db, simulation, "basilic")
    assert current is not None
    assert current.status == "ouverte"

    all_alerts = list_alerts(db, simulation, "basilic")
    assert len(all_alerts) == 2
    assert {a.status for a in all_alerts} == {"ouverte", "clôturée"}


def test_plants_are_isolated_for_alerts(db, config):
    simulation = next_simulation()
    # Thym : seuil bas = 20 %, réarmement = 25 %
    # Romarin : seuil bas = 25 %, réarmement = 30 %
    save_message(db, make_telemetry(simulation, "thym", moisture=18.0, tick=1, revision=1), config=config)
    save_message(db, make_telemetry(simulation, "romarin", moisture=35.0, tick=1, revision=1), config=config)

    assert active_alert(db, simulation, "thym") is not None
    assert active_alert(db, simulation, "romarin") is None
    assert active_alert(db, simulation, "basilic") is None


def test_duplicate_telemetry_does_not_duplicate_alerts_or_events(db, config):
    simulation = next_simulation()
    m = make_telemetry(simulation, "basilic", moisture=30.0, tick=1, revision=1)
    assert save_message(db, m, config=config) is True
    # Re-livraison QoS 1 identique
    assert save_message(db, m, config=config) is False

    with Session(db) as session:
        alert_count = session.scalar(select(func.count()).select_from(AlertRow))
        event_count = session.scalar(select(func.count()).select_from(GreenhouseEventRow))
        reading_count = session.scalar(select(func.count()).select_from(GreenhouseReading))

    assert reading_count == 1
    assert alert_count == 1
    assert event_count == 1


def test_events_limit_and_order(db, config):
    simulation = next_simulation()
    # Génère plusieurs événements manuels
    for i in range(15):
        m = make_telemetry(simulation, "thym", moisture=22.0 + i, tick=i, revision=i, origin="modification_manuelle")
        save_message(db, m, config=config)

    all_events = list_events(db, simulation, "thym", limit=10)
    assert len(all_events) == 10
    # Ordre strictement décroissant de séquence
    sequences = [e.sequence for e in all_events]
    assert sequences == sorted(sequences, reverse=True)


def test_transaction_rollback_prevents_partial_alert_state(db):
    simulation = next_simulation()
    m = make_telemetry(simulation, "basilic", moisture=30.0, tick=1, revision=1)

    class BrokenConfig:
        def get_plant(self, _):
            raise RuntimeError("Erreur forcée pour tester le rollback atomique.")

    with pytest.raises(RuntimeError, match="Erreur forcée"):
        save_message(db, m, config=BrokenConfig())

    with Session(db) as session:
        assert session.scalar(select(func.count()).select_from(GreenhouseReading)) == 0
        assert session.scalar(select(func.count()).select_from(AlertRow)) == 0
        assert session.scalar(select(func.count()).select_from(GreenhouseEventRow)) == 0


@pytest.mark.parametrize('current_moisture,late_moisture', [(50.0, 30.0), (30.0, 50.0)])
@pytest.mark.parametrize('same_revision', [False, True])
def test_late_measurement_preserves_current_alert_and_journal(
    db, config, current_moisture, late_moisture, same_revision,
):
    from greenmind.db.readings import latest_reading
    simulation = next_simulation()
    current = make_telemetry(simulation, moisture=current_moisture, tick=2, revision=2)
    current = current.model_copy(update={'emitted_at': current.emitted_at + timedelta(seconds=10)})
    save_message(db, current, config=config)
    events_before = [e.event_id for e in list_events(db, simulation)]
    alert_before = active_alert(db, simulation, 'basilic')
    late = make_telemetry(simulation, moisture=late_moisture, tick=1,
                          revision=2 if same_revision else 1, origin='modification_manuelle')
    assert save_message(db, late, config=config)
    assert latest_reading(db, simulation, 'basilic').event_id == str(current.event_id)
    alert_after = active_alert(db, simulation, 'basilic')
    assert (alert_after.alert_id if alert_after else None) == (alert_before.alert_id if alert_before else None)
    assert [e.event_id for e in list_events(db, simulation)] == events_before
    assert len(recent_readings(db, simulation, 'basilic')) == 2
