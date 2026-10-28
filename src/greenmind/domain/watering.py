"""Calcul d'arrosage pédagogique partagé par l'API et le simulateur."""

from dataclasses import dataclass
from math import isfinite
from greenmind.greenhouse_config import BedProfile


@dataclass(frozen=True)
class WateringPlan:
    watering_duration_s: float
    moist_after_pct: float
    duration_limited: bool
    reason: str


def plan_watering(profile: BedProfile, moisture: float) -> WateringPlan:
    if not isfinite(moisture) or not 0 <= moisture <= 100:
        raise ValueError("L'humidité doit être finie et comprise entre 0 et 100.")
    if moisture >= profile.moist_low_pct:
        raise ValueError("Le bac n'est pas sous son seuil bas ; aucun arrosage proposé.")
    requested = (profile.moist_target_pct - moisture) / profile.watering_gain_pct_per_s
    duration = min(profile.watering_max_duration_s, requested)
    duration_limited = requested > profile.watering_max_duration_s
    after = min(100.0, moisture + duration * profile.watering_gain_pct_per_s)
    reason = (f"{profile.display_name} : humidité {moisture:g} % sous le seuil "
              f"{profile.moist_low_pct:g} % ; arrosage de {duration:g} secondes virtuelles.")
    if duration_limited:
        reason += f" Durée plafonnée ; la cible {profile.moist_target_pct:g} % ne sera pas atteinte."
    return WateringPlan(duration, after, duration_limited, reason)
