"""Vérification réutilisable de l'environnement GreenMind."""

import os
import subprocess
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

REQUIRED_PACKAGES = (
    "paho-mqtt",
    "pydantic",
    "SQLAlchemy",
    "PyYAML",
    "pytest",
    "fastapi",
    "uvicorn",
)

EXPECTED_ENVIRONMENT = {
    "OMP_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
    "OPENBLAS_NUM_THREADS": "1",
    "TOKENIZERS_PARALLELISM": "false",
}

REQUIRED_FILES = (
    "requirements.lock.txt",
    "scripts/runtime_env.sh",
    "scripts/check_database.py",
    "docker-compose.yml",
    "docker/mosquitto.conf",
    "config/greenhouse.yaml",
    "data/fixtures/weather_greenhouse_day.csv",
    "data/readme.md",
    "docs/contracts.md",
    "src/greenmind/greenhouse_config.py",
    "src/greenmind/schemas.py",
    "src/greenmind/domain/simulation.py",
    "src/greenmind/simulator/weather.py",
    "src/greenmind/simulator/main.py",
    "src/greenmind/db/models.py",
    "src/greenmind/db/session.py",
)


def main() -> int:
    """Retourne zéro si les contrôles réussissent, un sinon."""
    failures = []

    def report(success: bool, message: str) -> None:
        label = "OK" if success else "ÉCHEC"
        print(f"[{label}] {message}", flush=True)
        if not success:
            failures.append(message)

    print("=== Environnement Python ===")
    print(f"Projet : {PROJECT_ROOT}")
    print(f"Interpréteur : {sys.executable}")
    print(f"Version : {sys.version.split()[0]}")

    report(
        sys.version_info[:2] == (3, 12),
        "Python 3.12 utilisé.",
    )
    report(
        sys.prefix != sys.base_prefix,
        "Environnement virtuel actif.",
    )
    report(
        Path(sys.prefix).resolve() == (PROJECT_ROOT / ".venv").resolve(),
        "Environnement virtuel appartenant à ce projet.",
    )

    print("\n=== Dépendances de J2 ===")
    for package in REQUIRED_PACKAGES:
        try:
            installed_version = version(package)
        except PackageNotFoundError:
            report(False, f"Dépendance absente : {package}.")
        else:
            report(True, f"{package} : {installed_version}")

    print("\n=== Cohérence des dépendances ===")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "check"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except subprocess.TimeoutExpired:
        report(False, "La vérification des dépendances dépasse 30 secondes.")
    except OSError:
        report(False, "Impossible de lancer la vérification des dépendances.")
    else:
        report(
            result.returncode == 0,
            "Vérification de cohérence des dépendances avec pip.",
        )
        if result.returncode != 0:
            print("Diagnostic de pip, dans la langue de l'outil :")
            diagnostic = "\n".join(
                output.strip()
                for output in (result.stdout, result.stderr)
                if output.strip()
            )
            print(diagnostic or "Aucun diagnostic fourni.")

    print("\n=== Paramètres de stabilité hérités ===")
    for name, expected in EXPECTED_ENVIRONMENT.items():
        actual = os.environ.get(name)
        displayed = actual if actual is not None else "non défini"
        report(
            actual == expected,
            f"{name} : {displayed} ; valeur attendue : {expected}.",
        )

    print("\n=== Fichiers nécessaires à l'étape actuelle ===")
    for relative_path in REQUIRED_FILES:
        report(
            (PROJECT_ROOT / relative_path).is_file(),
            f"Présence de {relative_path}",
        )

    print("\n=== Bilan ===")
    if failures:
        print(f"VÉRIFICATION ÉCHOUÉE : {len(failures)} contrôle(s) en échec.")
        return 1

    print("TEST RÉUSSI : les contrôles de l'environnement sont satisfaits.")
    print(
        "Ce contrôle ne remplace pas les tests MQTT, SQLite, IA "
        "ni les tests automatisés du projet."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())