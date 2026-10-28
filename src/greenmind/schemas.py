"""Contrats MQTT v2 de la serre ; aucun message v1 n'est accepté ici."""

from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal, Self
from uuid import UUID, uuid4

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from greenmind.greenhouse_config import PlantId
from greenmind.greenhouse_config import Percentage

Provenance = Literal["synthetic_weather_plus_synthetic_soil", "historical_weather_plus_synthetic_soil"]
from greenmind.simulator.engine import SimulationSnapshot


class WireModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, allow_inf_nan=False)
    schema_version: Annotated[int, Field(ge=2, le=2)] = 2


class TelemetryV2(WireModel):
    event_id: UUID
    run_id: UUID
    plant_id: PlantId
    observed_at: AwareDatetime
    simulated_at: AwareDatetime
    emitted_at: AwareDatetime
    simulated_tick: Annotated[int, Field(ge=0, le=24)]
    state_revision: Annotated[int, Field(ge=0)]
    paused: bool
    completed: bool
    air_temperature_c: float
    air_humidity_pct: Percentage
    soil_moisture_sim_pct: Percentage
    pump_active: bool
    provenance: Provenance
    measurement_origin: Literal["initial", "model", "manual_override", "watering", "heartbeat"]

    @field_validator("observed_at", "simulated_at", "emitted_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def coherent_state(self) -> Self:
        if self.state_revision < self.simulated_tick:
            raise ValueError("La révision ne peut pas précéder le pas simulé.")
        if self.completed != (self.simulated_tick == 24) or (self.completed and not self.paused):
            raise ValueError("La fin de journée doit correspondre au pas 24 en pause.")
        offset = timedelta(hours=1 if self.simulated_tick else 0)
        if self.simulated_at != self.observed_at + offset:
            raise ValueError("L'heure virtuelle doit correspondre à l'intervalle météo appliqué.")
        if self.measurement_origin == "initial" and (self.simulated_tick or self.state_revision):
            raise ValueError("Une mesure initiale doit être au pas et à la révision zéro.")
        return self


class SimulationControl(WireModel):
    control_id: UUID
    run_id: UUID
    expected_revision: Annotated[int, Field(ge=0)]
    action: Literal["PAUSE", "RESUME", "ADVANCE", "SET_SOIL_MOISTURE"]
    requested_at: AwareDatetime
    expires_at: AwareDatetime
    plant_id: PlantId | None = None
    value: Percentage | None = None

    @field_validator("requested_at", "expires_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def validate_arguments(self) -> Self:
        if not timedelta(0) < self.expires_at - self.requested_at <= timedelta(seconds=60):
            raise ValueError("Un contrôle doit expirer entre 0 et 60 secondes après sa demande.")
        if self.action == "SET_SOIL_MOISTURE":
            if self.plant_id is None or self.value is None:
                raise ValueError("Le bac et la valeur sont obligatoires pour imposer l'humidité.")
        elif self.plant_id is not None or self.value is not None:
            raise ValueError("Cette action n'accepte ni bac ni valeur.")
        return self


class SimulationEvent(WireModel):
    event_id: UUID
    run_id: UUID
    control_id: UUID | None = None
    status: Literal["STATE", "APPLIED", "REJECTED"]
    state_revision: Annotated[int, Field(ge=0)]
    simulated_tick: Annotated[int, Field(ge=0, le=24)]
    simulated_at: AwareDatetime
    emitted_at: AwareDatetime
    paused: bool
    completed: bool
    reason: str


def parse_v2(model, payload):
    try:
        # Le numéro doit être explicite sur le réseau, malgré la valeur par défaut Python.
        result = model.model_validate_json(payload)
        if "schema_version" not in result.model_fields_set:
            raise ValueError("Le champ schema_version est obligatoire sur le réseau.")
        return result
    except ValidationError as error:
        fields = sorted({".".join(map(str, item["loc"])) or "JSON" for item in error.errors()})
        raise ValueError("Message v2 invalide. Vérifier : " + ", ".join(fields) + ".") from error


def telemetry_for_snapshot(snapshot: SimulationSnapshot, origin: str) -> tuple[TelemetryV2, ...]:
    """Trois événements corrélés au même état ; chaque republication est nouvelle."""
    now = datetime.now(timezone.utc)
    return tuple(TelemetryV2(
        event_id=uuid4(), run_id=snapshot.run_id, plant_id=plant_id,
        observed_at=snapshot.weather.observed_at, simulated_at=snapshot.simulated_at,
        emitted_at=now, simulated_tick=snapshot.simulated_tick,
        state_revision=snapshot.state_revision, paused=snapshot.paused,
        completed=snapshot.completed, air_temperature_c=snapshot.weather.air_temperature_c,
        air_humidity_pct=snapshot.weather.air_humidity_pct, soil_moisture_sim_pct=value,
        pump_active=False, provenance=snapshot.weather.provenance, measurement_origin=origin,
    ) for plant_id, value in snapshot.soil_values)


class WateringCommand(WireModel):
    command_id: UUID
    run_id: UUID
    plant_id: PlantId
    actuator_id: str
    duration_sim_s: Annotated[float, Field(gt=0, le=10)]
    expected_revision: Annotated[int, Field(ge=0)]
    requested_at: AwareDatetime
    expires_at: AwareDatetime

    @field_validator('requested_at', 'expires_at')
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        return value.astimezone(timezone.utc)

    @model_validator(mode='after')
    def coherent_command(self) -> Self:
        from greenmind.greenhouse_config import IDENTITIES
        if self.actuator_id != IDENTITIES[self.plant_id][1]:
            raise ValueError("L'arroseur doit correspondre au bac ciblé.")
        if not timedelta(0) < self.expires_at - self.requested_at <= timedelta(seconds=60):
            raise ValueError("La commande doit expirer dans les 60 secondes réelles.")
        return self


class WateringEvent(WireModel):
    event_id: UUID
    command_id: UUID
    run_id: UUID
    plant_id: PlantId
    actuator_id: str
    status: Literal['APPLIED', 'REJECTED']
    resulting_revision: Annotated[int, Field(ge=0)]
    simulated_at: AwareDatetime
    emitted_at: AwareDatetime
    soil_moisture_after_pct: Percentage
    duration_applied_sim_s: Annotated[float, Field(ge=0, le=10)]
    reason: str

    @field_validator('simulated_at', 'emitted_at')
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        return value.astimezone(timezone.utc)

    @model_validator(mode='after')
    def coherent_result(self) -> Self:
        from greenmind.greenhouse_config import IDENTITIES
        if self.actuator_id != IDENTITIES[self.plant_id][1]:
            raise ValueError("L'arroseur doit correspondre au bac ciblé.")
        if (self.status == 'APPLIED') != (self.duration_applied_sim_s > 0):
            raise ValueError("Seul un arrosage appliqué possède une durée positive.")
        return self
