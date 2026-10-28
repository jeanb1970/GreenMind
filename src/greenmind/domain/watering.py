"""Calcul d'arrosage pédagogique partagé par l'API et le simulateur."""

from dataclasses import dataclass
from math import isfinite
from greenmind.greenhouse_config import BedProfile


@dataclass(frozen=True)
class WateringPlan:
    duration_sim_s: float
    soil_moisture_after_pct: float
    capped: bool
    reason: str


def plan_watering(profile: BedProfile, moisture: float) -> WateringPlan:
    if not isfinite(moisture) or not 0 <= moisture <= 100:
        raise ValueError("L'humidité doit être finie et comprise entre 0 et 100.")
    if moisture >= profile.low_threshold_sim_pct:
        raise ValueError("Le bac n'est pas sous son seuil bas ; aucun arrosage proposé.")
    requested = (profile.target_soil_moisture_sim_pct - moisture) / profile.irrigation_gain_per_sim_s
    duration = min(profile.max_watering_duration_sim_s, requested)
    capped = requested > profile.max_watering_duration_sim_s
    after = min(100.0, moisture + duration * profile.irrigation_gain_per_sim_s)
    reason = (f"{profile.display_name} : humidité {moisture:g} % sous le seuil "
              f"{profile.low_threshold_sim_pct:g} % ; arrosage de {duration:g} secondes virtuelles.")
    if capped:
        reason += f" Durée plafonnée ; la cible {profile.target_soil_moisture_sim_pct:g} % ne sera pas atteinte."
    return WateringPlan(duration, after, capped, reason)
