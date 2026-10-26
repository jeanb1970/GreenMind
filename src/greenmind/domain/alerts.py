"""Règles déterministes du cycle de l'alerte de sécheresse."""


def next_dry_alert_state(
    soil_moisture_sim_pct: float,
    *,
    alert_open: bool,
    low_threshold_sim_pct: float,
    rearm_threshold_sim_pct: float,
) -> bool:
    """Retourne True si l'alerte doit être ouverte après cette mesure.

    Les valeurs doivent être validées par les contrats d'entrée :
    humidité et seuils finis, entre 0 et 100, seuil bas strictement
    inférieur au seuil de réarmement.

    Cette fonction ne réalise aucune écriture en base.
    """
    if alert_open:
        return soil_moisture_sim_pct <= rearm_threshold_sim_pct

    return soil_moisture_sim_pct < low_threshold_sim_pct