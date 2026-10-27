"""Tests de lecture et de validation des données météo."""

from pathlib import Path

import pytest

from greenmind.simulator.weather import load_weather


HEADER = (
    "observed_at,air_temperature_c,air_humidity_pct,provenance\n"
)
PROVENANCE = "synthetic_weather_plus_synthetic_soil"


def write_weather(tmp_path, content):
    """Crée un fichier météo temporaire propre au test."""
    path = tmp_path / "weather.csv"
    path.write_text(content, encoding="utf-8")
    return path


def test_project_fixture():
    project_root = Path(__file__).resolve().parents[1]
    path = project_root / "data" / "fixtures" / "weather_greenhouse_day.csv"

    readings = load_weather(path)

    assert len(readings) == 24, (
        "La fixture de démonstration doit contenir 24 lignes."
    )
    assert all(reading.provenance == PROVENANCE for reading in readings)
    assert len({reading.air_temperature_c for reading in readings}) > 1
    assert len({reading.air_humidity_pct for reading in readings}) > 1



@pytest.mark.parametrize(
    "content, expected_message",
    [
        (
            "",
            "aucun en-tête",
        ),
        (
            HEADER,
            "aucune donnée",
        ),
        (
            "observed_at,air_temperature_c\n",
            "Colonnes météo manquantes",
        ),
        (
            HEADER
            + f"2026-07-10T00:00:00Z,25,101,{PROVENANCE}\n",
            "l'humidité de l'air doit être entre 0 et 100",
        ),
        (
            HEADER
            + f"2026-07-10T00:00:00Z,chaud,50,{PROVENANCE}\n",
            "doivent être numériques",
        ),
        (
            HEADER
            + f"2026-07-10T00:00:00Z,nan,50,{PROVENANCE}\n",
            "doivent être finies",
        ),
        (
            HEADER
            + f"2026-07-10T00:00:00,25,50,{PROVENANCE}\n",
            "doit préciser son fuseau horaire",
        ),
        (
            HEADER
            + f"date-invalide,25,50,{PROVENANCE}\n",
            "date invalide",
        ),
        (
            HEADER
            + "2026-07-10T00:00:00Z,25,50,origine_inconnue\n",
            "provenance inconnue",
        ),
        (
            HEADER
            + f"2026-07-10T00:00:00Z,25,50,{PROVENANCE}\n"
            + f"2026-07-10T00:00:00Z,25,50,{PROVENANCE}\n",
            "strictement croissantes",
        ),
        (
            HEADER
            + f"2026-07-10T01:00:00Z,25,50,{PROVENANCE}\n"
            + f"2026-07-10T00:00:00Z,25,50,{PROVENANCE}\n",
            "strictement croissantes",
        ),
        (
            HEADER
            + "2026-07-10T00:00:00Z,25,50\n",
            "nombre de champs incorrect",
        ),
    ],
)
def test_invalid_file_is_rejected(tmp_path, content, expected_message):
    path = write_weather(tmp_path, content)

    with pytest.raises(ValueError, match=expected_message):
        load_weather(path)


def test_missing_file_is_rejected(tmp_path):
    path = tmp_path / "absent.csv"

    with pytest.raises(ValueError, match="Impossible de lire le fichier météo"):
        load_weather(path)


def test_timezone_is_converted_to_utc(tmp_path):
    path = write_weather(
        tmp_path,
        HEADER + f"2026-07-10T02:00:00+02:00,25,50,{PROVENANCE}\n",
    )

    reading = load_weather(path)[0]

    assert reading.observed_at.isoformat() == "2026-07-10T00:00:00+00:00", (
        "L'heure météo doit être convertie en UTC sans changer l'instant."
    )