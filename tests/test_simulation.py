import pytest

from greenmind.domain.simulation import dry_one_tick


@pytest.fixture
def profile():
    return {"moist_initial_pct": 40.0, "moist_low_pct": 35.0,
            "simulation": {"base_evaporation_per_tick": 4.0,
                           "reference_temperature_c": 20.0,
                           "temperature_factor_per_c": 0.05}}


def test_drying_is_reproducible_and_crosses_threshold(profile):
    def replay():
        moisture = profile["moist_initial_pct"]
        history = [moisture]
        for _ in range(3):
            moisture = dry_one_tick(
                moisture, 25.0, 50.0, **profile["simulation"]
            )
            history.append(moisture)
        return history

    history = replay()

    assert history == replay(), (
        "La simulation doit produire les mêmes résultats à chaque exécution."
    )
    assert history == pytest.approx([40.0, 37.5, 35.0, 32.5]), (
        "L'évolution de l'humidité ne correspond pas au scénario attendu."
    )
    assert history[2] >= profile["moist_low_pct"], (
        "Le seuil bas ne doit pas être franchi avant le troisième pas."
    )
    assert history[3] < profile["moist_low_pct"], (
        "L'humidité doit être sous le seuil bas au troisième pas."
    )


def test_long_drought_stops_at_zero(profile):
    moisture = 100.0
    for _ in range(1000):
        moisture = dry_one_tick(
            moisture, 40.0, 0.0, **profile["simulation"]
        )
        assert 0.0 <= moisture <= 100.0, (
            "L'humidité simulée doit rester comprise entre 0 et 100."
        )

    assert moisture == 0.0, (
        "Après une sécheresse prolongée, l'humidité doit atteindre zéro."
    )


def test_weather_affects_drying(profile):
    parameters = profile["simulation"]

    cool = dry_one_tick(40.0, 20.0, 50.0, **parameters)
    hot = dry_one_tick(40.0, 30.0, 50.0, **parameters)
    humid = dry_one_tick(40.0, 30.0, 80.0, **parameters)

    assert hot < cool, (
        "À humidité de l'air identique, la chaleur doit accentuer le dessèchement."
    )
    assert hot < humid, (
        "À température identique, un air plus humide doit réduire le dessèchement."
    )


@pytest.mark.parametrize(
    "soil, temperature, humidity",
    [
        (-1.0, 25.0, 50.0),
        (101.0, 25.0, 50.0),
        (40.0, 25.0, -1.0),
        (40.0, 25.0, 101.0),
        (float("nan"), 25.0, 50.0),
        (40.0, float("inf"), 50.0),
    ],
)
def test_invalid_measurements_are_rejected(
    profile, soil, temperature, humidity
):
    with pytest.raises(ValueError):
        dry_one_tick(
            soil, temperature, humidity, **profile["simulation"]
        )
