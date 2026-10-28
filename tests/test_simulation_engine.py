"""Preuves B2 : temps virtuel, pause, interventions et journée reproductible."""

from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from greenmind.domain.greenhouse import dry_greenhouse_one_hour
from greenmind.greenhouse_config import load_greenhouse_config
from greenmind.simulator.engine import SimulationEngine, SCENARIO_TIMEZONE
from greenmind.simulator.weather import load_weather


ROOT = Path(__file__).resolve().parents[1]


class Clock:
    now = 0.0

    def __call__(self):
        return self.now


@pytest.fixture
def setup():
    config = load_greenhouse_config(ROOT / "config/greenhouse.yaml")
    weather = load_weather(ROOT / "data/fixtures/weather_greenhouse_day.csv")
    clock = Clock()
    return config, weather, clock, SimulationEngine(config, weather, clock=clock)


def test_daily_weather_shape_and_provenance(setup):
    _, weather, _, engine = setup
    temperatures = [r.air_temperature_c for r in weather]
    humidities = [r.air_humidity_pct for r in weather]
    assert min(temperatures) == 18.0 and max(temperatures) == 32.0
    assert temperatures.index(max(temperatures)) == 14
    assert min(humidities) == 40.0 and max(humidities) == 82.0
    assert temperatures[5] < temperatures[10] < temperatures[14]
    assert temperatures[14] > temperatures[18] > temperatures[23]
    assert all(r.provenance == "meteo_simulee" for r in weather)
    state = engine.snapshot()
    assert state.simulated_at.astimezone(SCENARIO_TIMEZONE).isoformat() == "2026-07-10T00:00:00+02:00"
    assert state.paused and not state.day_complete
    assert state.heure_virtuelle == state.current_state == 0


def test_pause_and_snapshot_cannot_change_state(setup):
    _, _, clock, engine = setup
    before = engine.snapshot()
    clock.now = 5000.0
    assert engine.poll() is None
    assert engine.pause() is None
    copy = before.soil
    copy["basilic"] = 0.0
    assert engine.snapshot() == before
    with pytest.raises(FrozenInstanceError):
        before.paused = False


def test_first_hour_uses_first_interval_not_second(setup):
    config, weather, _, engine = setup
    start = engine.snapshot()
    change = engine.advance_one_hour()
    assert change.before == start
    assert change.after.simulated_at == start.simulated_at + timedelta(hours=1)
    assert change.after.weather == weather[0]
    assert change.after.soil == dry_greenhouse_one_hour(config, start.soil, 20.0, 75.0)
    assert change.after.current_state == 1


def test_full_day_automatic_and_manual_have_identical_values(setup):
    config, weather, clock, manual = setup
    auto = SimulationEngine(config, weather, clock=clock)
    auto.resume()
    assert auto.snapshot().simulation != manual.snapshot().simulation
    for hour in range(1, 25):
        expected = manual.advance_one_hour().after
        clock.now = hour * 5.0 - 0.01
        assert auto.poll() is None
        clock.now = hour * 5.0
        event = auto.poll()
        assert event is not None
        actual = event.after
        assert actual.soil == expected.soil
        assert actual.simulated_at == expected.simulated_at
        assert actual.weather == weather[hour - 1]
        assert actual.heure_virtuelle == hour
        assert all(0 <= v <= 100 for v in actual.soil.values())
        assert auto.poll() is None
    assert actual.day_complete and actual.paused
    assert actual.simulated_at.astimezone(SCENARIO_TIMEZONE).isoformat() == "2026-07-11T00:00:00+02:00"
    clock.now += 10000
    assert auto.poll() is None
    for action in (auto.resume, auto.advance_one_hour):
        with pytest.raises(ValueError, match="terminée"):
            action()


def test_resume_discards_pause_time_and_duplicate_resume_keeps_deadline(setup):
    _, _, clock, engine = setup
    engine.resume()
    clock.now = 4.0
    assert engine.resume() is None
    clock.now = 5.0
    assert engine.poll() is not None
    engine.pause()
    clock.now = 1000.0
    assert engine.poll() is None
    engine.resume()
    assert engine.poll() is None
    clock.now += 5.0
    assert engine.poll().after.heure_virtuelle == 2


def test_delayed_poll_does_not_skip_intervals_or_burst(setup):
    _, weather, clock, engine = setup
    engine.resume()
    clock.now = 1000.0
    event = engine.poll()
    assert event.after.heure_virtuelle == 1
    assert event.after.weather == weather[0]
    assert engine.poll() is None
    clock.now += 5.0
    assert engine.poll().after.weather == weather[1]


def test_manual_override_preserves_history_time_and_other_beds(setup):
    config, weather, _, engine = setup
    engine.advance_one_hour()
    before = engine.snapshot()
    change = engine.set_soil_moisture("thym", 18.0)
    assert change.kind == "modification_manuelle" and change.plant_id == "thym"
    assert change.before == before
    assert change.after.soil == {**before.soil, "thym": 18.0}
    assert change.after.simulated_at == before.simulated_at
    assert change.after.heure_virtuelle == before.heure_virtuelle
    assert change.after.current_state == before.current_state + 1
    assert before.soil["thym"] != 18.0
    expected = dry_greenhouse_one_hour(
        config, change.after.soil, weather[1].air_temperature_c, weather[1].air_humidity_pct,
    )
    assert engine.advance_one_hour().after.soil == expected


@pytest.mark.parametrize("value", [-1, 101, float("nan"), float("inf"), True, "32", None])
def test_invalid_override_leaves_state_unchanged(setup, value):
    engine = setup[3]
    before = engine.snapshot()
    with pytest.raises(ValueError, match="humidité"):
        engine.set_soil_moisture("basilic", value)
    assert engine.snapshot() == before


@pytest.mark.parametrize("value", [0, 100])
def test_override_accepts_boundary_values(setup, value):
    engine = setup[3]
    assert engine.set_soil_moisture("basilic", value).after.soil["basilic"] == value


def test_invalid_target_and_running_mutations_are_rejected(setup):
    engine = setup[3]
    with pytest.raises(ValueError, match="inconnue"):
        engine.set_soil_moisture("tomate_01", 32.0)
    engine.resume()
    before = engine.snapshot()
    with pytest.raises(ValueError, match="pause"):
        engine.advance_one_hour()
    with pytest.raises(ValueError, match="pause"):
        engine.set_soil_moisture("basilic", 32.0)
    assert engine.snapshot() == before


@pytest.mark.parametrize("now", [-1.0, float("nan"), float("inf")])
def test_bad_real_clock_does_not_advance(setup, now):
    _, _, clock, engine = setup
    engine.resume()
    before = engine.snapshot()
    clock.now = now
    with pytest.raises(ValueError, match="monotone"):
        engine.poll()
    assert engine.snapshot() == before


@pytest.mark.parametrize("problem", ["missing", "gap", "not_midnight", "nan", "humidity", "provenance", "naive", "dst"])
def test_invalid_day_is_rejected(setup, problem):
    config, weather, _, _ = setup
    if problem == "missing":
        weather.pop()
    elif problem == "gap":
        weather[8] = replace(weather[8], observed_at=weather[8].observed_at + timedelta(minutes=1))
    elif problem == "not_midnight":
        weather = [replace(r, observed_at=r.observed_at + timedelta(hours=1)) for r in weather]
    elif problem == "naive":
        weather[0] = replace(weather[0], observed_at=weather[0].observed_at.replace(tzinfo=None))
    elif problem == "dst":
        start = datetime(2026, 3, 28, 23, tzinfo=timezone.utc)
        weather = [replace(r, observed_at=start + timedelta(hours=i)) for i, r in enumerate(weather)]
    elif problem == "nan":
        weather[0] = replace(weather[0], air_temperature_c=float("nan"))
    elif problem == "humidity":
        weather[0] = replace(weather[0], air_humidity_pct=101.0)
    else:
        weather[0] = replace(weather[0], provenance="inconnue")
    with pytest.raises(ValueError):
        SimulationEngine(config, weather)
