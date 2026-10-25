"""Tests du chargement de la configuration du basilic."""

from pathlib import Path

import pytest
import yaml

from greenmind.config import load_plant_config


@pytest.fixture
def config_data():
    project_root = Path(__file__).resolve().parents[1]
    path = project_root / "config" / "plants.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def write_config(tmp_path, data):
    """Enregistre une configuration temporaire pour un test."""
    path = tmp_path / "plants.yaml"
    path.write_text(
        yaml.safe_dump(data, allow_unicode=True),
        encoding="utf-8",
    )
    return path


def test_valid_config(tmp_path, config_data):
    path = write_config(tmp_path, config_data)

    config = load_plant_config(path)

    assert config.plant_id == "basilic_01", (
        "La configuration doit identifier le basilic."
    )
    assert config.initial_soil_moisture_sim_pct == 40.0, (
        "L'humidité initiale du scénario doit être de 40 %."
    )
    assert config.low_threshold_sim_pct < config.high_threshold_sim_pct, (
        "Le seuil bas doit être inférieur au seuil haut."
    )


@pytest.mark.parametrize(
    "section, field, value, expected_message",
    [
        (
            None, "initial_soil_moisture_sim_pct", 101.0,
            "initial_soil_moisture_sim_pct",
        ),
        (
            "simulation", "base_evaporation_per_tick", -1.0,
            "simulation.base_evaporation_per_tick",
        ),
        (
            "simulation", "temperature_factor_per_c", -0.1,
            "simulation.temperature_factor_per_c",
        ),
        (
            None, "low_threshold_sim_pct", 65.0,
            "Le seuil bas",
        ),
        (
            None, "low_threshold_sim_pct", 70.0,
            "Le seuil bas",
        ),
        (
            None, "display_name", "   ",
            "display_name",
        ),
        (
            None, "plant_id", "romarin_01",
            "plant_id",
        ),
        (
            None, "unknown_parameter", 10,
            "unknown_parameter",
        ),
    ],
)
def test_invalid_config_is_rejected(
    tmp_path, config_data, section, field, value, expected_message
):
    target = config_data if section is None else config_data[section]
    target[field] = value
    path = write_config(tmp_path, config_data)

    with pytest.raises(ValueError) as caught:
        load_plant_config(path)

    assert expected_message in str(caught.value), (
        "L'erreur doit identifier le paramètre incorrect "
        "ou expliquer l'incohérence des seuils."
    )


def test_empty_config_is_rejected(tmp_path):
    path = tmp_path / "plants.yaml"
    path.write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="doit contenir des paramètres YAML"):
        load_plant_config(path)


def test_missing_config_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="Impossible de lire la configuration"):
        load_plant_config(tmp_path / "absent.yaml")


def test_invalid_yaml_is_rejected(tmp_path):
    path = tmp_path / "plants.yaml"
    path.write_text("simulation: [", encoding="utf-8")

    with pytest.raises(ValueError, match="syntaxe YAML invalide"):
        load_plant_config(path)