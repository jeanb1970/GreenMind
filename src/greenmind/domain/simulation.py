"""Calcul déterministe du dessèchement d'un substrat virtuel."""

from math import isfinite


def dry_one_tick(
    soil_moisture_pct: float,
    air_temperature_c: float,
    air_humidity_pct: float,
    *,
    base_evaporation_per_tick: float,
    reference_temperature_c: float,
    temperature_factor_per_c: float,
) -> float:
    """Retourne l'humidité après un pas, sur une échelle simulée 0–100.

    Modèle pédagogique non calibré :
    - la chaleur au-dessus de la référence accélère le dessèchement ;
    - l'humidité de l'air réduit le dessèchement ;
    - aucun arrosage n'est traité à cette étape.
    """
    values = (
        soil_moisture_pct,
        air_temperature_c,
        air_humidity_pct,
        base_evaporation_per_tick,
        reference_temperature_c,
        temperature_factor_per_c,
    )
    if not all(isfinite(value) for value in values):
        raise ValueError("Les valeurs doivent être des nombres finis.")

    if not 0.0 <= soil_moisture_pct <= 100.0:
        raise ValueError("L'humidité du substrat doit être entre 0 et 100.")

    if not 0.0 <= air_humidity_pct <= 100.0:
        raise ValueError("L'humidité de l'air doit être entre 0 et 100.")

    if base_evaporation_per_tick < 0.0 or temperature_factor_per_c < 0.0:
        raise ValueError("Les coefficients doivent être positifs ou nuls.")

    temperature_excess = max(
        air_temperature_c - reference_temperature_c,
        0.0,
    )
    heat_factor = 1.0 + temperature_factor_per_c * temperature_excess
    dryness_factor = 1.0 - air_humidity_pct / 100.0

    evaporation = (
        base_evaporation_per_tick * heat_factor * dryness_factor
    )
    return max(0.0, min(100.0, soil_moisture_pct - evaporation))
