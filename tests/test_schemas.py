"""Tests du contrat de télémétrie GreenMind."""

import json

import pytest

from greenmind.schemas import parse_telemetry


@pytest.fixture
def payload():
    """Retourne un nouveau message valide pour chaque test."""
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


def test_valid_message_round_trip(payload):
    message = parse_telemetry(json.dumps(payload))

    assert message.plant_id == "basilic_01", (
        "L'identifiant du basilic doit être conservé."
    )
    assert message.soil_moisture_sim_pct == 37.5, (
        "L'humidité simulée doit être conservée."
    )
    assert parse_telemetry(message.model_dump_json()) == message, (
        "La conversion en JSON puis la relecture doivent conserver le message."
    )


@pytest.mark.parametrize(
    "field, value",
    [
        ("event_id", "identifiant-invalide"),
        ("schema_version", 2),
        ("schema_version", True),
        ("plant_id", "romarin_01"),
        ("simulated_tick", 0),
        ("simulated_tick", 1.5),
        ("simulated_tick", True),
        ("air_temperature_c", "25"),
        ("air_humidity_pct", -1.0),
        ("air_humidity_pct", 101.0),
        ("soil_moisture_sim_pct", -1.0),
        ("soil_moisture_sim_pct", 101.0),
        ("pump_active", "false"),
        ("provenance", "origine_inconnue"),
        ("observed_at", "2026-07-10T00:00:00"),
        ("emitted_at", "date-invalide"),
    ],
)
def test_invalid_field_is_rejected(payload, field, value):
    payload[field] = value

    with pytest.raises(ValueError, match=field):
        parse_telemetry(json.dumps(payload))


@pytest.mark.parametrize(
    "field",
    [
        "event_id",
        "schema_version",
        "plant_id",
        "observed_at",
        "emitted_at",
        "simulated_tick",
        "air_temperature_c",
        "air_humidity_pct",
        "soil_moisture_sim_pct",
        "pump_active",
        "provenance",
    ],
)
def test_missing_field_is_rejected(payload, field):
    del payload[field]

    with pytest.raises(ValueError, match=field):
        parse_telemetry(json.dumps(payload))


def test_unknown_field_is_rejected(payload):
    payload["unexpected_field"] = "valeur"

    with pytest.raises(ValueError, match="unexpected_field"):
        parse_telemetry(json.dumps(payload))


def test_invalid_json_is_rejected():
    with pytest.raises(ValueError, match="document JSON"):
        parse_telemetry("{message incomplet")


def test_timezone_is_normalized(payload):
    payload["observed_at"] = "2026-07-10T02:00:00+02:00"

    message = parse_telemetry(json.dumps(payload))

    assert message.observed_at.isoformat() == "2026-07-10T00:00:00+00:00", (
        "La date doit être convertie en UTC sans changer l'instant."
    )


@pytest.mark.parametrize("value", [0.0, 100.0])
def test_percentage_boundaries_are_accepted(payload, value):
    payload["air_humidity_pct"] = value
    payload["soil_moisture_sim_pct"] = value

    message = parse_telemetry(json.dumps(payload))

    assert message.air_humidity_pct == value, (
        "Les bornes 0 et 100 doivent être acceptées pour l'humidité de l'air."
    )
    assert message.soil_moisture_sim_pct == value, (
        "Les bornes 0 et 100 doivent être acceptées pour l'humidité du substrat."
    )