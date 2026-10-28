"""Profils de référence de la serre à trois bacs."""

from pathlib import Path
from typing import Annotated, Literal, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

Percentage = Annotated[float, Field(ge=0, le=100)]
NonNegative = Annotated[float, Field(ge=0)]


PlantId = Literal["basilic", "thym", "romarin"]
IDENTITIES = {
    "basilic": ("bac_basilic", "arroseur_basilic"),
    "thym": ("bac_thym", "arroseur_thym"),
    "romarin": ("bac_romarin", "arroseur_romarin"),
}
Positive = Annotated[float, Field(gt=0)]


class BedProfile(BaseModel):
    """Un profil représente toute une rangée et son arroseur dédié."""

    model_config = ConfigDict(
        strict=True, extra="forbid", frozen=True,
        allow_inf_nan=False, str_strip_whitespace=True,
    )

    plant_id: PlantId
    bed_id: str
    arroseur_id: str
    display_name: Annotated[str, Field(min_length=1)]
    moist_initial_pct: Percentage
    moist_low_pct: Percentage
    moist_rearm_pct: Percentage
    moist_high_pct: Percentage
    moist_target_pct: Percentage
    evaporation_pct_per_hour: Positive
    reference_temperature_c: float
    temperature_factor_per_c: NonNegative
    watering_gain_pct_per_s: Positive
    watering_max_duration_s: Annotated[float, Field(gt=0, le=10)]
    watering_rest_s: Positive

    @model_validator(mode="after")
    def validate_profile(self) -> Self:
        if (self.bed_id, self.arroseur_id) != IDENTITIES[self.plant_id]:
            raise ValueError("Le bac et l'arroseur doivent correspondre à la plante.")
        if not (
            self.moist_low_pct < self.moist_rearm_pct
            < self.moist_target_pct <= self.moist_high_pct
        ):
            raise ValueError(
                "Les seuils doivent respecter : bas < réarmement < cible ≤ haut."
            )
        return self


class GreenhouseConfig(BaseModel):
    """Collection immuable contenant exactement les trois profils attendus."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    scenario: Literal["journee_serre"]
    plants: tuple[BedProfile, ...]

    @field_validator("plants", mode="before")
    @classmethod
    def freeze_yaml_list(cls, value):
        # YAML fournit une liste ; la configuration exposée reste immuable.
        return tuple(value) if isinstance(value, list) else value

    @model_validator(mode="after")
    def validate_collection(self) -> Self:
        for name in ("plant_id", "bed_id", "arroseur_id"):
            values = [getattr(profile, name) for profile in self.plants]
            if len(values) != len(set(values)):
                raise ValueError(f"Identifiant dupliqué dans la serre : {name}.")
        if {profile.plant_id for profile in self.plants} != set(IDENTITIES):
            raise ValueError("La serre doit contenir le basilic, le thym et le romarin.")
        return self

    def get_plant(self, plant_id: str) -> BedProfile:
        for profile in self.plants:
            if profile.plant_id == plant_id:
                return profile
        raise ValueError(f"Plante inconnue dans la serre : {plant_id}.")


def load_greenhouse_config(path: Path) -> GreenhouseConfig:
    """Charge le YAML et traduit les diagnostics de validation en français."""
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise ValueError(f"Impossible de lire la configuration UTF-8 de la serre : {path}.") from error
    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as error:
        raise ValueError("La configuration de la serre présente une syntaxe YAML invalide.") from error
    if not isinstance(data, dict):
        raise ValueError("La configuration de la serre doit contenir des paramètres YAML.")
    try:
        return GreenhouseConfig.model_validate(data)
    except ValidationError as error:
        details = []
        for item in error.errors():
            location = ".".join(str(part) for part in item["loc"]) or "serre"
            reason = item.get("ctx", {}).get("error")
            details.append(f"{location} : {reason}" if reason else location)
        raise ValueError(
            "Configuration de la serre invalide. Paramètres à vérifier : "
            + "; ".join(details) + "."
        ) from error
