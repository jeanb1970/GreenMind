"""Lecture et validation du fichier météo local."""

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from math import isfinite
from pathlib import Path


REQUIRED_COLUMNS = {
    "observed_at",
    "air_temperature_c",
    "air_humidity_pct",
    "provenance",
}

ALLOWED_PROVENANCES = {
    "synthetic_weather_plus_synthetic_soil",
    "historical_weather_plus_synthetic_soil",
}


@dataclass(frozen=True)
class WeatherReading:
    """Une ligne météo validée, indépendante de l'horloge réelle."""

    observed_at: datetime
    air_temperature_c: float
    air_humidity_pct: float
    provenance: str


def _parse_row(row: dict[str, str], line_number: int) -> WeatherReading:
    """Convertit une ligne CSV et signale précisément les erreurs."""
    prefix = f"Ligne météo {line_number}"

    try:
        observed_at = datetime.fromisoformat(row["observed_at"])
    except ValueError as error:
        raise ValueError(
            f"{prefix} : date invalide, format ISO 8601 attendu."
        ) from error

    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError(
            f"{prefix} : la date doit préciser son fuseau horaire."
        )

    try:
        temperature = float(row["air_temperature_c"])
        humidity = float(row["air_humidity_pct"])
    except ValueError as error:
        raise ValueError(
            f"{prefix} : température et humidité doivent être numériques."
        ) from error

    if not isfinite(temperature) or not isfinite(humidity):
        raise ValueError(
            f"{prefix} : température et humidité doivent être finies."
        )

    if not 0.0 <= humidity <= 100.0:
        raise ValueError(
            f"{prefix} : l'humidité de l'air doit être entre 0 et 100."
        )

    provenance = row["provenance"]
    if provenance not in ALLOWED_PROVENANCES:
        raise ValueError(
            f"{prefix} : provenance inconnue « {provenance} »."
        )

    return WeatherReading(
        observed_at=observed_at.astimezone(timezone.utc),
        air_temperature_c=temperature,
        air_humidity_pct=humidity,
        provenance=provenance,
    )


def load_weather(path: Path) -> list[WeatherReading]:
    """Charge le fichier entier ou lève une erreur sans résultat partiel."""
    readings: list[WeatherReading] = []

    try:
        with path.open(encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file, strict=True)
            columns = reader.fieldnames

            if not columns:
                raise ValueError("Le fichier météo ne contient aucun en-tête.")

            if len(columns) != len(set(columns)):
                raise ValueError("Le fichier météo contient des colonnes dupliquées.")

            missing = REQUIRED_COLUMNS - set(columns)
            if missing:
                raise ValueError(
                    "Colonnes météo manquantes : "
                    + ", ".join(sorted(missing))
                )

            for row in reader:
                line_number = reader.line_num

                if None in row or any(value is None for value in row.values()):
                    raise ValueError(
                        f"Ligne météo {line_number} : nombre de champs incorrect."
                    )

                clean_row = {
                    key: value.strip()
                    for key, value in row.items()
                }
                reading = _parse_row(clean_row, line_number)

                if readings and reading.observed_at <= readings[-1].observed_at:
                    raise ValueError(
                        f"Ligne météo {line_number} : les dates doivent être "
                        "strictement croissantes, sans doublon."
                    )

                readings.append(reading)

    except OSError as error:
        raise ValueError(
            f"Impossible de lire le fichier météo : {path}."
        ) from error
    except UnicodeError as error:
        raise ValueError(
            "Le fichier météo doit être encodé en UTF-8."
        ) from error
    except csv.Error as error:
        raise ValueError(
            "Le fichier météo présente une structure CSV invalide."
        ) from error

    if not readings:
        raise ValueError("Le fichier météo ne contient aucune donnée.")

    return readings