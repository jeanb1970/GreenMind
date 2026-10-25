"""Tests de persistance et de dédoublonnage des mesures."""

import json

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from greenmind.db.models import SensorReading
from greenmind.db.readings import save_reading
from greenmind.db.session import create_database_engine
from greenmind.schemas import parse_telemetry


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
    database_engine = create_database_engine(tmp_path / "test.sqlite")
    try:
        yield database_engine
    finally:
        database_engine.dispose()


def test_reading_survives_database_reopening(tmp_path, payload):
    path = tmp_path / "persistent.sqlite"
    message = parse_telemetry(json.dumps(payload))

    first_engine = create_database_engine(path)
    try:
        assert save_reading(first_engine, message) is True, (
            "La première insertion doit enregistrer la mesure."
        )
    finally:
        first_engine.dispose()

    second_engine = create_database_engine(path)
    try:
        with Session(second_engine) as session:
            reading = session.get(SensorReading, str(message.event_id))

            assert reading is not None, (
                "La mesure doit être conservée après réouverture de la base."
            )
            assert reading.soil_moisture_sim_pct == 37.5, (
                "L'humidité enregistrée doit être conservée."
            )
            assert reading.provenance == payload["provenance"], (
                "La provenance doit être conservée."
            )
    finally:
        second_engine.dispose()


def test_duplicate_creates_only_one_reading(engine, payload):
    message = parse_telemetry(json.dumps(payload))

    assert save_reading(engine, message) is True, (
        "La première insertion doit réussir."
    )
    assert save_reading(engine, message) is False, (
        "La seconde insertion doit être identifiée comme un doublon."
    )

    with Session(engine) as session:
        count = session.scalar(
            select(func.count()).select_from(SensorReading)
        )

    assert count == 1, (
        "Deux insertions du même événement doivent produire une seule ligne."
    )


def test_existing_event_is_not_overwritten(engine, payload):
    message = parse_telemetry(json.dumps(payload))
    save_reading(engine, message)

    payload["soil_moisture_sim_pct"] = 80.0
    conflicting_message = parse_telemetry(json.dumps(payload))

    assert save_reading(engine, conflicting_message) is False, (
        "Un identifiant déjà enregistré ne doit pas être réinséré."
    )

    with Session(engine) as session:
        reading = session.get(SensorReading, str(message.event_id))
        assert reading is not None, (
            "La mesure initiale doit toujours exister après réception du doublon."
        )
        assert reading.soil_moisture_sim_pct == 37.5, (
            "Un événement portant le même identifiant ne doit pas "
            "écraser la mesure initiale."
        )


def test_dates_are_stored_in_fixed_utc_format(engine, payload):
    payload["observed_at"] = "2026-07-10T02:00:00+02:00"
    message = parse_telemetry(json.dumps(payload))

    save_reading(engine, message)

    with Session(engine) as session:
        reading = session.get(SensorReading, str(message.event_id))
        assert reading is not None, (
            "La mesure doit être enregistrée avant de vérifier ses dates."
        )
        assert reading.observed_at == "2026-07-10T00:00:00.000000Z", (
            "L'heure météo doit être enregistrée en UTC "
            "avec six chiffres de microsecondes."
        )
        assert reading.emitted_at == "2026-10-25T13:00:00.000000Z", (
            "L'heure d'émission doit utiliser le même format UTC fixe."
        )