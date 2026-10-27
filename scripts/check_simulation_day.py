"""Démonstration locale B2, automatique pas à pas ou interactive au clavier."""

import argparse
from pathlib import Path
from time import sleep

from greenmind.greenhouse_config import load_greenhouse_config
from greenmind.simulator.engine import SimulationEngine, SCENARIO_TIMEZONE
from greenmind.simulator.weather import load_weather


def show(engine: SimulationEngine) -> None:
    state = engine.snapshot()
    moment = state.simulated_at.astimezone(SCENARIO_TIMEZONE)
    weather_hour = state.weather.observed_at.astimezone(SCENARIO_TIMEZONE)
    values = " | ".join(f"{name} : {value:.2f} %" for name, value in state.soil.items())
    mode = "terminée" if state.completed else "pause" if state.paused else "lecture"
    print(
        f"{moment:%d/%m %H:%M} | {mode} | pas {state.simulated_tick} | "
        f"révision {state.state_revision}\n"
        f"  Météo de l'intervalle {weather_hour:%H:%M} : "
        f"{state.weather.air_temperature_c:g} °C / "
        f"{state.weather.air_humidity_pct:g} % d'humidité de l'air\n  {values}"
    )


def interactive(engine: SimulationEngine) -> None:
    print(
        "Commandes : heure, etat, lecture, humidite <plante> <valeur>, quitter.\n"
        "Plantes : basilic_01, thym_01, romarin_01.\n"
        "Pendant la lecture : Ctrl+C met en pause ; une heure toutes les 5 secondes."
    )
    while True:
        try:
            parts = input("Simulation > ").split()
            if not parts:
                continue
            if parts == ["quitter"]:
                return
            if parts == ["heure"]:
                engine.advance_one_hour()
            elif parts == ["lecture"]:
                engine.resume()
                try:
                    while not engine.snapshot().paused:
                        if engine.poll() is not None:
                            show(engine)
                        sleep(0.1)
                except KeyboardInterrupt:
                    engine.pause()
                    print("Lecture mise en pause.")
            elif len(parts) == 3 and parts[0] == "humidite":
                try:
                    value = float(parts[2].replace(",", "."))
                except ValueError:
                    raise ValueError("Saisir une humidité numérique entre 0 et 100.") from None
                change = engine.set_soil_moisture(parts[1], value)
                print(
                    f"Humidité imposée : {change.before.soil[parts[1]]:g} → "
                    f"{change.after.soil[parts[1]]:g} %, heure virtuelle inchangée."
                )
            elif parts != ["etat"]:
                print("Commande inconnue. Utiliser heure, etat, lecture, humidite ou quitter.")
                continue
            show(engine)
        except ValueError as error:
            print(f"Action refusée : {error}")
        except (EOFError, KeyboardInterrupt):
            print("\nFin du contrôle local.")
            return


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.add_argument("-h", "--help", action="help", help="Afficher cette aide et quitter.")
    parser.add_argument("--interactive", action="store_true", help="Piloter la simulation au clavier.")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    engine = SimulationEngine(
        load_greenhouse_config(root / "config/greenhouse.yaml"),
        load_weather(root / "data/fixtures/weather_greenhouse_day.csv"),
    )
    print("B2 — Journée synthétique illustrative — ambiance de serre.")
    print("Contrôle local : aucune publication MQTT, écriture SQL ou commande d'arrosage.")
    show(engine)
    if args.interactive:
        interactive(engine)
        return
    print("Parcours en 24 avances manuelles, sans attente réelle ; extrait toutes les 6 heures.")
    for hour in range(1, 25):
        engine.advance_one_hour()
        if hour % 6 == 0:
            show(engine)
    print("Fin de journée : arrêt en pause, sans boucle automatique.")


if __name__ == "__main__":
    main()
