"""Contrôle local de la brique B1, sans broker ni écriture en base."""

from pathlib import Path

from greenmind.domain.alerts import next_dry_alert_state
from greenmind.domain.greenhouse import initial_soil_state, dry_greenhouse_one_hour
from greenmind.greenhouse_config import load_greenhouse_config


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    config = load_greenhouse_config(root / "config/greenhouse.yaml")
    initial = initial_soil_state(config)
    after = dry_greenhouse_one_hour(config, initial, 25.0, 50.0)
    print("B1 — Trois bacs virtuels ; valeurs pédagogiques non agronomiques.")
    print("Une heure simulée sous une même météo : 25 °C, humidité de l'air 50 %.")
    for plant in config.plants:
        dry = next_dry_alert_state(
            32.0, alert_open=False,
            low_threshold_sim_pct=plant.low_threshold_sim_pct,
            rearm_threshold_sim_pct=plant.rearm_threshold_sim_pct,
        )
        print(
            f"{plant.display_name} | {plant.bed_id} | {plant.actuator_id} | "
            f"{initial[plant.plant_id]:g} → {after[plant.plant_id]:g} % | "
            f"à 32 % : {'alerte' if dry else 'pas de nouvelle alerte'}"
        )
    print("Ce contrôle local ne publie aucune mesure MQTT et ne commande aucun arroseur.")


if __name__ == "__main__":
    main()
