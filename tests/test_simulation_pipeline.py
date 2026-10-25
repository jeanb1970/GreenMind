"""Vérification du raccordement des composants du simulateur."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from greenmind.config import load_plant_config
from greenmind.domain.simulation import dry_one_tick
from greenmind.schemas import TelemetryMessage, parse_telemetry
from greenmind.simulator.weather import load_weather


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_fixture_produces_expected_telemetry():
    """Rejoue les 24 lignes et vérifie les messages produits."""
    config = load_plant_config(PROJECT_ROOT / "config/plants.yaml")
    weather = load_weather(
        PROJECT_ROOT / "data/fixtures/weather_sample.csv"
    )

    assert len(weather) == 24, (
        "Le scénario de démonstration doit contenir 24 lignes météo."
    )

    weather_start = datetime(2026, 7, 10, tzinfo=timezone.utc)

    # Horloge fixe réservée à ce test, distincte de la météo rejouée.
    emission_start = datetime(2026, 10, 25, 13, tzinfo=timezone.utc)

    moisture = config.initial_soil_moisture_sim_pct
    history = []
    event_ids = set()

    assert moisture == 40.0, (
        "Le scénario actuel doit démarrer avec une humidité de 40 %."
    )

    for tick, reading in enumerate(weather, start=1):
        expected_observed_at = weather_start + timedelta(hours=tick - 1)

        assert reading.observed_at == expected_observed_at, (
            f"Au pas {tick}, l'heure météo ne correspond pas "
            "à la séquence horaire documentée."
        )

        moisture = dry_one_tick(
            moisture,
            reading.air_temperature_c,
            reading.air_humidity_pct,
            **config.simulation.model_dump(),
        )

        emitted_at = emission_start + timedelta(seconds=5 * (tick - 1))

        message = TelemetryMessage(
            event_id=uuid4(),
            schema_version=1,
            plant_id=config.plant_id,
            observed_at=reading.observed_at,
            emitted_at=emitted_at,
            simulated_tick=tick,
            air_temperature_c=reading.air_temperature_c,
            air_humidity_pct=reading.air_humidity_pct,
            soil_moisture_sim_pct=moisture,
            pump_active=False,
            provenance=reading.provenance,
        )

        # Relecture du JSON comme le fera le service d'ingestion.
        received = parse_telemetry(message.model_dump_json())

        assert received == message, (
            f"Au pas {tick}, la conversion JSON doit conserver "
            "l'intégralité de la mesure."
        )
        assert received.event_id not in event_ids, (
            "Chaque nouvel événement doit avoir un identifiant distinct."
        )
        assert received.provenance == "synthetic_weather_plus_synthetic_soil", (
            "La provenance synthétique doit être conservée."
        )
        assert received.pump_active is False, (
            "La pompe doit rester inactive pendant ce scénario de dessèchement."
        )

        event_ids.add(received.event_id)
        history.append(received.soil_moisture_sim_pct)

    expected_history = [
        max(0.0, 40.0 - 2.5 * tick)
        for tick in range(1, 25)
    ]

    assert history == expected_history, (
        "Les 24 humidités doivent correspondre au scénario constant documenté."
    )
    assert history[1] == config.low_threshold_sim_pct, (
        "Le deuxième pas doit atteindre le seuil bas."
    )
    assert history[2] < config.low_threshold_sim_pct, (
        "Le troisième pas doit franchir le seuil bas."
    )