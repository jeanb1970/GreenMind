"""Tests du raccordement entre télémétrie reçue et persistance SQL."""

import json

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from greenmind.db.models import SensorReading
from greenmind.db.session import create_database_engine
from greenmind.ingestion.handler import ingest_telemetry


TOPIC = "greenmind/v1/plants/basilic_01/telemetry"


@pytest.fixture
def payload():
    return {
        "event_id": "3dd6b710-66f2-4243-8a24-725a03a22800",
        "schema_version": 1,
        "plant_id": "basilic_01",
        "observed_at": "2026-07-10T00:00:00Z",
        "emitted_at": "2026-10-25T13:00:00Z",
        "simulated_tick": 1,
        "air_temperature_c": 25.0,
        "air_humidity_pct": 50.0,
        "soil_moisture_sim_pct": 37.5,
        "pump_active": False,
        "provenance": "synthetic_weather_plus_synthetic_soil",
    }


@pytest.fixture
def engine(tmp_path):
    database_engine = create_database_engine(tmp_path / "ingestion.sqlite")
    try:
        yield database_engine
    finally:
        database_engine.dispose()


def count_readings(engine):
    """Compte les mesures présentes dans la base de test."""
    with Session(engine) as session:
        return session.scalar(
            select(func.count()).select_from(SensorReading)
        )


def test_valid_message_is_saved(engine, payload):
    raw_payload = json.dumps(payload).encode("utf-8")

    assert ingest_telemetry(engine, TOPIC, raw_payload) is True, (
        "Une télémétrie valide reçue en octets doit être enregistrée."
    )

    with Session(engine) as session:
        reading = session.get(SensorReading, payload["event_id"])
        assert reading is not None, (
            "L'événement reçu doit être présent en base."
        )
        assert reading.soil_moisture_sim_pct == 37.5, (
            "L'humidité reçue doit être conservée."
        )


def test_duplicate_is_identified(engine, payload):
    raw_payload = json.dumps(payload)

    assert ingest_telemetry(engine, TOPIC, raw_payload) is True, (
        "La première réception doit insérer la mesure."
    )
    assert ingest_telemetry(engine, TOPIC, raw_payload) is False, (
        "La seconde réception doit être identifiée comme un doublon."
    )
    assert count_readings(engine) == 1, (
        "Un doublon ne doit pas créer une deuxième mesure."
    )


def test_inconsistent_topic_is_rejected(engine, payload):
    wrong_topic = "greenmind/v1/plants/tomate_01/telemetry"

    with pytest.raises(ValueError, match="Topic de télémétrie invalide"):
        ingest_telemetry(engine, wrong_topic, json.dumps(payload))

    assert count_readings(engine) == 0, (
        "Un topic incohérent ne doit provoquer aucune insertion."
    )


def test_invalid_message_does_not_prevent_next_message(engine, payload):
    with pytest.raises(ValueError, match="Message de télémétrie invalide"):
        ingest_telemetry(engine, TOPIC, b"{")

    assert count_readings(engine) == 0, (
        "Un JSON invalide ne doit provoquer aucune insertion."
    )
    assert ingest_telemetry(engine, TOPIC, json.dumps(payload)) is True, (
        "Un message valide suivant le rejet doit pouvoir être enregistré."
    )


def test_database_failure_is_not_reported_as_duplicate(
    engine, payload, monkeypatch
):
    def fail_to_save(engine, message):
        raise OperationalError(
            "INSERT",
            {},
            RuntimeError("Panne SQL simulée pour le test."),
        )

    monkeypatch.setattr(
        "greenmind.ingestion.handler.save_reading",
        fail_to_save,
    )

    with pytest.raises(OperationalError):
        ingest_telemetry(engine, TOPIC, json.dumps(payload))

    assert count_readings(engine) == 0, (
        "La panne simulée ne doit enregistrer aucune mesure."
    )