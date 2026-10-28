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
    assert len({p.arroseur_id for p in config.plants}) == 3
    assert isinstance(config.plants, tuple)
    with pytest.raises(ValidationError):
        config.plants[0].moist_low_pct = 0.0
    with pytest.raises(ValueError, match="Plante inconnue"):
        config.get_plant("tomate_01")


@pytest.mark.parametrize("change, message", [
    (lambda d: d["plants"].pop(), "doit contenir"),
    (lambda d: d["plants"].append(d["plants"][0]), "dupliqué"),
    (lambda d: d["plants"][0].update(plant_id="tomate_01"), "plant_id"),
    (lambda d: d["plants"][0].update(arroseur_id="arroseur_thym"), "correspondre"),
    (lambda d: d["plants"][0].update(bed_id="bac_romarin"), "correspondre"),
    (lambda d: d["plants"][0].update(moist_low_pct=40.0), "seuils"),
    (lambda d: d["plants"][0].update(moist_target_pct=40.0), "seuils"),
    (lambda d: d["plants"][0].update(moist_target_pct=70.0), "seuils"),
    (lambda d: d["plants"][0].update(moist_initial_pct=101.0), "moist_initial"),
    (lambda d: d["plants"][0].update(evaporation_pct_per_hour=0.0), "evaporation"),
    (lambda d: d["plants"][0].update(watering_gain_pct_per_s=-1.0), "watering_gain"),
    (lambda d: d["plants"][0].update(reference_temperature_c=float("nan")), "temperature"),
    (lambda d: d["plants"][0].update(watering_gain_pct_per_s=float("inf")), "watering_gain"),
    (lambda d: d["plants"][0].update(watering_max_duration_s=11.0), "duration"),
    (lambda d: d["plants"][0].update(watering_rest_s=0.0), "watering_rest"),
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
        "basilic": 47.5, "thym": 33.75, "romarin": 38.4375,
    })
    assert result == dry_greenhouse_one_hour(config, initial, 25.0, 50.0)
    assert initial == {"basilic": 50.0, "thym": 35.0, "romarin": 40.0}


def test_states_do_not_leak_between_beds_or_runs(config):
    first = initial_soil_state(config)
    second = initial_soil_state(config)
    first["basilic"] = 32.0
    result = dry_greenhouse_one_hour(config, first, 25.0, 50.0)
    reference = dry_greenhouse_one_hour(config, second, 25.0, 50.0)
    assert second["basilic"] == 50.0
    assert result["basilic"] != reference["basilic"]
    assert result["thym"] == reference["thym"]
    assert result["romarin"] == reference["romarin"]


def test_same_humidity_only_triggers_basilic(config):
    alerts = {
        p.plant_id: next_dry_alert_state(
            32.0, alert_open=False,
            moist_low_pct=p.moist_low_pct,
            moist_rearm_pct=p.moist_rearm_pct,
        ) for p in config.plants
    }
    assert alerts == {"basilic": True, "thym": False, "romarin": False}


@pytest.mark.parametrize("invalid", [float("nan"), -1.0, 101.0])
def test_invalid_soil_state_is_rejected_without_mutation(config, invalid):
    state = initial_soil_state(config)
    state["romarin"] = invalid
    with pytest.raises(ValueError):
        dry_greenhouse_one_hour(config, state, 25.0, 50.0)
    assert state["basilic"] == 50.0


def test_missing_bed_in_state_is_rejected(config):
    state = initial_soil_state(config)
    del state["thym"]
    with pytest.raises(ValueError, match="exactement les trois"):
        dry_greenhouse_one_hour(config, state, 25.0, 50.0)
