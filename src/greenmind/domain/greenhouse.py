"""États indépendants et évolution horaire pure des trois bacs."""

from collections.abc import Mapping

from greenmind.domain.simulation import dry_one_tick
from greenmind.greenhouse_config import GreenhouseConfig


def initial_soil_state(config: GreenhouseConfig) -> dict[str, float]:
    """Retourne un nouvel état, indépendant des autres exécutions."""
    return {
        plant.plant_id: plant.moist_initial_pct
        for plant in config.plants
    }


def dry_greenhouse_one_hour(
    config: GreenhouseConfig,
    soil_state: Mapping[str, float],
    air_temperature_c: float,
    air_humidity_pct: float,
) -> dict[str, float]:
    """Calcule une heure sous météo commune sans modifier l'état reçu.

    Le pas de dry_one_tick correspond ici exactement à une heure virtuelle.
    Aucun délai réel, message MQTT ou effet d'arrosage n'intervient dans ce calcul.
    """
    if set(soil_state) != {plant.plant_id for plant in config.plants}:
        raise ValueError("L'état doit contenir exactement les trois bacs configurés.")
    return {
        plant.plant_id: dry_one_tick(
            soil_state[plant.plant_id], air_temperature_c, air_humidity_pct,
            base_evaporation_per_tick=plant.evaporation_pct_per_hour,
            reference_temperature_c=plant.reference_temperature_c,
            temperature_factor_per_c=plant.temperature_factor_per_c,
        )
        for plant in config.plants
    }
