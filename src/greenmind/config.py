"""Chargement et validation de la configuration du basilic."""

from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError


Percentage = Annotated[float, Field(ge=0.0, le=100.0)]
NonNegative = Annotated[float, Field(ge=0.0)]


class SimulationConfig(BaseModel):
    """Coefficients du modèle pédagogique de dessèchement."""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        allow_inf_nan=False,
        frozen=True,
    )

    base_evaporation_per_tick: NonNegative
    reference_temperature_c: float
    temperature_factor_per_c: NonNegative


class PlantConfig(BaseModel):
    """Configuration de référence du basilic virtuel."""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        allow_inf_nan=False,
        frozen=True,
        str_strip_whitespace=True,
    )

    plant_id: Literal["basilic_01"]
    display_name: Annotated[str, Field(min_length=1)]
    scenario: Literal["demo_dry_basil"]
    initial_soil_moisture_sim_pct: Percentage
    low_threshold_sim_pct: Percentage
    rearm_threshold_sim_pct: Percentage
    high_threshold_sim_pct: Percentage
    simulation: SimulationConfig


def load_plant_config(path: Path) -> PlantConfig:
    """Lit le YAML et retourne une configuration validée."""
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as error:
        raise ValueError(
            f"Impossible de lire la configuration de la plante : {path}."
        ) from error
    except UnicodeError as error:
        raise ValueError(
            "La configuration de la plante doit être encodée en UTF-8."
        ) from error

    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as error:
        raise ValueError(
            "La configuration de la plante présente une syntaxe YAML invalide."
        ) from error

    if not isinstance(data, dict):
        raise ValueError(
            "La configuration de la plante doit contenir des paramètres YAML."
        )

    try:
        config = PlantConfig.model_validate(data)
    except ValidationError as error:
        fields = sorted({
            ".".join(str(part) for part in item["loc"])
            or "configuration"
            for item in error.errors()
        })
        raise ValueError(
            "Configuration de la plante invalide. "
            "Paramètres à vérifier : "
            + ", ".join(fields)
            + "."
        ) from error

    if config.low_threshold_sim_pct >= config.high_threshold_sim_pct:
        raise ValueError(
            "Le seuil bas d'humidité doit être strictement inférieur "
            "au seuil haut."
        )

    if config.rearm_threshold_sim_pct <= config.low_threshold_sim_pct:
        raise ValueError(
            "Le seuil de réarmement doit être strictement supérieur "
            "au seuil bas."
        )

    if config.rearm_threshold_sim_pct > config.high_threshold_sim_pct:
        raise ValueError(
            "Le seuil de réarmement doit être inférieur ou égal "
            "au seuil haut."
        )

    return config
