"""Vérification de la brique B4 : REST API, alertes multi-bacs et journal d'événements.

Valide la chaîne complète : simulateur MQTT -> broker Mosquitto -> ingestion ->
persistance atomique SQLite -> API REST FastAPI (/api/v1).
"""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from time import monotonic, sleep
from fastapi.testclient import TestClient

from greenmind.api.app import create_app
from greenmind.api.dependencies import get_db, get_publisher, MqttPublisher
from greenmind.db.models import GreenhouseReading
from greenmind.db.readings import latest_reading
from greenmind.db.session import create_database_engine
from sqlalchemy import select
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]


def wait_for(predicate, description, timeout=15):
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        result = predicate()
        if result:
            return result
        sleep(0.05)
    raise RuntimeError(f"Délai dépassé : {description}.")


def main() -> int:
    processes = []
    logs = []
    db = None
    passed = False

    with tempfile.TemporaryDirectory(prefix="greenmind-b4-") as directory:
        directory = Path(directory)
        try:
            db_path = directory / "greenmind_b4.sqlite"
            db = create_database_engine(db_path)
            env = dict(
                os.environ,
                PYTHONPATH=str(ROOT / "src"),
                GREENMIND_DATABASE_PATH=str(db_path),
            )

            def start(module, name):
                logfile = directory / f"{name}.log"
                handle = logfile.open("w")
                logs.append((logfile, handle))
                proc = subprocess.Popen(
                    [sys.executable, "-m", module],
                    cwd=ROOT,
                    env=env,
                    stdout=handle,
                    stderr=subprocess.STDOUT,
                )
                processes.append(proc)
                return proc, logfile

            # 1. Démarrage de l'ingestion et du simulateur
            ingestion, ingestion_log = start("greenmind.ingestion.main", "ingestion")
            wait_for(lambda: "Ingestion prête" in ingestion_log.read_text(), "abonnement ingestion")

            simulator, simulator_log = start("greenmind.simulator.main", "simulateur")

            # Attendre les 3 mesures initiales en base
            def initial_ready():
                with Session(db) as session:
                    rows = list(session.scalars(select(GreenhouseReading).where(
                        GreenhouseReading.measurement_origin == "initial"
                    )))
                    return rows if len(rows) == 3 else None

            rows = wait_for(initial_ready, "trois mesures initiales en base")
            simulation = rows[0].simulation

            # 2. Instanciation de l'API REST FastAPI avec le moteur SQLite du test
            app = create_app(simulation_mode=True)
            app.dependency_overrides[get_db] = lambda: db
            app.dependency_overrides[get_publisher] = lambda: MqttPublisher()
            client = TestClient(app)

            # Test 1 : GET /api/v1/health
            res = client.get("/api/v1/health")
            if res.status_code != 200 or not res.json().get("database_connected"):
                raise RuntimeError(f"Échec /health : {res.text}")
            print("OK : API REST initialisée et connectée à SQLite.", flush=True)

            # Test 2 : GET /api/v1/plants (trois bacs, pas d'alerte initiale)
            res = client.get("/api/v1/plants")
            if res.status_code != 200 or len(res.json()) != 3:
                raise RuntimeError(f"Échec /plants : {res.text}")
            plants = {p["plant_id"]: p for p in res.json()}
            if any(p["has_active_alert"] for p in plants.values()):
                raise RuntimeError("Une alerte est anormalement active à l'état initial.")
            print("OK : trois bacs consultables via REST sans alerte initiale.", flush=True)

            # Test 3 : GET /api/v1/plants/basilic (détail et seuils)
            res = client.get("/api/v1/plants/basilic")
            if res.status_code != 200 or res.json().get("moist_low_pct") != 35.0:
                raise RuntimeError(f"Échec /plants/basilic : {res.text}")
            print("OK : profil et seuils du bac vérifiés par REST.", flush=True)

            # Test 4 : Injection critique via POST /api/v1/simulation/controls
            # Thym seuil bas = 20 % -> injection à 18 %
            current_rev = plants["basilic"]["current_state"]
            res = client.post("/api/v1/simulation/controls", json={
                "action": "modifier_humidite_sol",
                "expected_state": current_rev,
                "plant_id": "thym",
                "moist_request_pct": 18.0,
            })
            if res.status_code != 202:
                raise RuntimeError(f"Échec POST control : {res.status_code} {res.text}")
            control_id = res.json()["control_id"]

            # Attendre acquittement APPLIED via GET /api/v1/simulation/controls/{control_id}
            def control_applied():
                r = client.get(f"/api/v1/simulation/controls/{control_id}")
                return r.json() if r.json().get("status") == "appliqué" else None

            wait_for(control_applied, "application du contrôle de forçage thym")

            # Le rejeu REST doit retrouver la commande d'origine même après
            # l'évolution de révision et conserver son acquittement APPLIED.
            retry = client.post("/api/v1/simulation/controls", json={
                "control_id": control_id,
                "action": "modifier_humidite_sol",
                "expected_state": current_rev,
                "plant_id": "thym",
                "moist_request_pct": 18.0,
            })
            if retry.status_code != 202 or not control_applied():
                raise RuntimeError("Le rejeu idempotent du contrôle REST a échoué.")
            collision = client.post("/api/v1/simulation/controls", json={
                "control_id": control_id,
                "action": "modifier_humidite_sol",
                "expected_state": current_rev,
                "plant_id": "thym",
                "moist_request_pct": 19.0,
            })
            if collision.status_code != 409:
                raise RuntimeError("Une clé de contrôle réutilisée avec un autre contenu doit être refusée.")
            print("OK : rejeu REST idempotent après acquittement ; collision de clé refusée.", flush=True)

            # Test 5 : Vérification de l'alerte ouverte via l'API REST
            res_thym = client.get("/api/v1/plants/thym")
            thym_data = res_thym.json()
            if not thym_data.get("has_active_alert"):
                raise RuntimeError("L'alerte de sécheresse du thym n'est pas ouverte via l'API.")
            alert = thym_data.get("active_alert")
            if alert is None or alert.get("status") != "ouverte" or alert.get("moist_trigger_pct") != 18.0:
                raise RuntimeError(f"Alerte thym incohérente : {alert}")

            # Vérifier l'isolation : basilic et romarin ne doivent pas être en alerte
            if client.get("/api/v1/plants/basilic").json().get("has_active_alert"):
                raise RuntimeError("Alerte propagée à tort au basilic.")
            print("OK : forçage 18 % -> ouverture d'alerte atomique sur le thym ; isolation vérifiée.", flush=True)

            # Test 6 : Vérification du journal des événements via GET /api/v1/events
            res_events = client.get("/api/v1/events?plant_id=thym")
            if res_events.status_code != 200:
                raise RuntimeError(f"Échec /events : {res_events.text}")
            events = res_events.json()
            if not any(e["event_type"] == "alerte_ouverte" for e in events):
                raise RuntimeError("Événement ALERT_OPENED absent du journal.")
            print("OK : journal des événements filtrable et traçable en base.", flush=True)

            # Test 7 : Réarmement et clôture d'alerte (injection à 30 % > seuil réarmement 25 %)
            rev_after_first = client.get("/api/v1/plants/basilic").json()["current_state"]
            res = client.post("/api/v1/simulation/controls", json={
                "action": "modifier_humidite_sol",
                "expected_state": rev_after_first,
                "plant_id": "thym",
                "moist_request_pct": 30.0,
            })
            if res.status_code != 202:
                raise RuntimeError(f"Échec réarmement control : {res.text}")
            rearm_id = res.json()["control_id"]

            def rearm_applied():
                r = client.get(f"/api/v1/simulation/controls/{rearm_id}")
                return r.json() if r.json().get("status") == "appliqué" else None

            wait_for(rearm_applied, "application réarmement thym")

            # Vérifier clôture de l'alerte
            res_thym_rearmed = client.get("/api/v1/plants/thym")
            if res_thym_rearmed.json().get("has_active_alert"):
                raise RuntimeError("L'alerte du thym aurait dû être fermée après 30 % d'humidité.")

            res_events_rearmed = client.get("/api/v1/events?plant_id=thym")
            if not any(e["event_type"] == "alerte_clôturée" for e in res_events_rearmed.json()):
                raise RuntimeError("Événement ALERT_CLOSED absent après réarmement.")
            print("OK : réarmement 30 % -> clôture atomique de l'alerte et consignation au journal.", flush=True)

            # Test 8 : Erreurs attendues (404, 409)
            if client.get("/api/v1/plants/inconnu").status_code != 404:
                raise RuntimeError("404 attendue pour bac inconnu.")
            conflict_res = client.post("/api/v1/simulation/controls", json={
                "action": "avancer_1_heure",
                "expected_state": 0,  # Révision périmée
            })
            if conflict_res.status_code != 409:
                raise RuntimeError("409 attendue pour conflit de révision.")
            print("OK : codes HTTP 404 et 409 vérifiés.", flush=True)

            passed = True
        except Exception as error:
            print(f"ÉCHEC de recette B4 : {error}", flush=True)
            for path, handle in logs:
                handle.flush()
                print(f"--- Log de {path.name} ---")
                print(path.read_text()[-3000:])
        finally:
            for proc in reversed(processes):
                if proc.poll() is None:
                    proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=2)
            for _, handle in logs:
                handle.close()
            if db:
                db.dispose()

    if passed:
        print("TEST RÉUSSI : Brique B4 validée (Alertes atomiques, journal d'événements et API REST /api/v1).")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
