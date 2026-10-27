"""Validation de la serre v1.4 et isolation des états des bacs."""

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from greenmind.domain.alerts import next_dry_alert_state
from greenmind.domain.greenhouse import initial_soil_state, dry_greenhouse_one_hour
from greenmind.greenhouse_config import load_greenhouse_config


CONFIG_PATH = Path(__file__).resolve().parents[1] / "config/greenhouse.yaml"


@pytest.fixture
def config():
    return load_greenhouse_config(CONFIG_PATH)


def write_changed_config(tmp_path, change):
    data = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    change(data)
    path = tmp_path / "greenhouse.yaml"
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return path


def test_profiles_and_configuration_are_immutable(config):
    assert len(config.plants) == 3
    assert len({p.actuator_id for p in config.plants}) == 3
    assert isinstance(config.plants, tuple)
    with pytest.raises(ValidationError):
        config.plants[0].low_threshold_sim_pct = 0.0
    with pytest.raises(ValueError, match="Plante inconnue"):
        config.get_plant("tomate_01")


@pytest.mark.parametrize("change, message", [
    (lambda d: d["plants"].pop(), "doit contenir"),
    (lambda d: d["plants"].append(d["plants"][0]), "dupliqué"),
    (lambda d: d["plants"][0].update(plant_id="tomate_01"), "plant_id"),
    (lambda d: d["plants"][0].update(actuator_id="arroseur_thym"), "correspondre"),
    (lambda d: d["plants"][0].update(bed_id="bac_romarin"), "correspondre"),
    (lambda d: d["plants"][0].update(low_threshold_sim_pct=40.0), "seuils"),
    (lambda d: d["plants"][0].update(target_soil_moisture_sim_pct=40.0), "seuils"),
    (lambda d: d["plants"][0].update(target_soil_moisture_sim_pct=70.0), "seuils"),
    (lambda d: d["plants"][0].update(initial_soil_moisture_sim_pct=101.0), "initial_soil"),
    (lambda d: d["plants"][0].update(base_evaporation_per_hour=0.0), "evaporation"),
    (lambda d: d["plants"][0].update(irrigation_gain_per_sim_s=-1.0), "irrigation_gain"),
    (lambda d: d["plants"][0].update(reference_temperature_c=float("nan")), "temperature"),
    (lambda d: d["plants"][0].update(irrigation_gain_per_sim_s=float("inf")), "irrigation_gain"),
    (lambda d: d["plants"][0].update(max_watering_duration_sim_s=11.0), "duration"),
    (lambda d: d["plants"][0].update(watering_cooldown_real_s=0.0), "cooldown"),
    (lambda d: d["plants"][0].update(display_name="  "), "display_name"),
    (lambda d: d["plants"][0].update(unexpected=True), "unexpected"),
])
def test_invalid_profiles_are_rejected(tmp_path, change, message):
    with pytest.raises(ValueError, match=message):
        load_greenhouse_config(write_changed_config(tmp_path, change))


@pytest.mark.parametrize("content, message", [
    ("", "paramètres YAML"),
    ("plants: [", "syntaxe YAML"),
    ("- basilic", "paramètres YAML"),
])
def test_invalid_yaml_is_explained(tmp_path, content, message):
    path = tmp_path / "greenhouse.yaml"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        load_greenhouse_config(path)


def test_missing_file_is_explained(tmp_path):
    with pytest.raises(ValueError, match="Impossible de lire"):
        load_greenhouse_config(tmp_path / "missing.yaml")


def test_shared_weather_produces_distinct_deterministic_states(config):
    initial = initial_soil_state(config)
    result = dry_greenhouse_one_hour(config, initial, 25.0, 50.0)
    assert result == pytest.approx({
        "basilic_01": 47.5, "thym_01": 33.75, "romarin_01": 38.4375,
    })
    assert result == dry_greenhouse_one_hour(config, initial, 25.0, 50.0)
    assert initial == {"basilic_01": 50.0, "thym_01": 35.0, "romarin_01": 40.0}


def test_states_do_not_leak_between_beds_or_runs(config):
    first = initial_soil_state(config)
    second = initial_soil_state(config)
    first["basilic_01"] = 32.0
    result = dry_greenhouse_one_hour(config, first, 25.0, 50.0)
    reference = dry_greenhouse_one_hour(config, second, 25.0, 50.0)
    assert second["basilic_01"] == 50.0
    assert result["basilic_01"] != reference["basilic_01"]
    assert result["thym_01"] == reference["thym_01"]
    assert result["romarin_01"] == reference["romarin_01"]


def test_same_humidity_only_triggers_basilic(config):
    alerts = {
        p.plant_id: next_dry_alert_state(
            32.0, alert_open=False,
            low_threshold_sim_pct=p.low_threshold_sim_pct,
            rearm_threshold_sim_pct=p.rearm_threshold_sim_pct,
        ) for p in config.plants
    }
    assert alerts == {"basilic_01": True, "thym_01": False, "romarin_01": False}


@pytest.mark.parametrize("invalid", [float("nan"), -1.0, 101.0])
def test_invalid_soil_state_is_rejected_without_mutation(config, invalid):
    state = initial_soil_state(config)
    state["romarin_01"] = invalid
    with pytest.raises(ValueError):
        dry_greenhouse_one_hour(config, state, 25.0, 50.0)
    assert state["basilic_01"] == 50.0


def test_missing_bed_in_state_is_rejected(config):
    state = initial_soil_state(config)
    del state["thym_01"]
    with pytest.raises(ValueError, match="exactement les trois"):
        dry_greenhouse_one_hour(config, state, 25.0, 50.0)
