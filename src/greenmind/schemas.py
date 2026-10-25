"""Contrats de données partagés entre les composants GreenMind."""

from datetime import datetime, timezone
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
)


Percentage = Annotated[float, Field(ge=0.0, le=100.0)]

Provenance = Literal[
    "synthetic_weather_plus_synthetic_soil",
    "historical_weather_plus_synthetic_soil",
]


class TelemetryMessage(BaseModel):
    """Une mesure du basilic conforme au contrat MQTT v1."""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        allow_inf_nan=False,
        frozen=True,
    )

    event_id: UUID
    schema_version: Annotated[int, Field(ge=1, le=1)]
    plant_id: Literal["basilic_01"]
    observed_at: AwareDatetime
    emitted_at: AwareDatetime
    simulated_tick: Annotated[int, Field(ge=1)]
    air_temperature_c: float
    air_humidity_pct: Percentage
    soil_moisture_sim_pct: Percentage
    pump_active: bool
    provenance: Provenance

    @field_validator("observed_at", "emitted_at")
    @classmethod
    def normalize_to_utc(cls, value: datetime) -> datetime:
        """Normalise en UTC une date dont le fuseau a été validé."""
        return value.astimezone(timezone.utc)


def parse_telemetry(payload: str | bytes) -> TelemetryMessage:
    """Valide un message JSON et fournit une erreur française."""
    try:
        return TelemetryMessage.model_validate_json(payload)
    except ValidationError as error:
        fields = sorted({
            ".".join(str(part) for part in item["loc"])
            or "document JSON"
            for item in error.errors()
        })
        raise ValueError(
            "Message de télémétrie invalide. "
            "Champs ou contenu à vérifier : "
            + ", ".join(fields)
            + "."
        ) from error