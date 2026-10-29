"""Contrats MQTT v3 de la serre ; seule la version 3 du schéma est acceptée."""
from greenmind.simulation_rules import SimulationAction
from greenmind.time_formats import BelgianTime, BelgianInstant
from greenmind.identifiers import next_id, SimulationId, EventId, ControlId, CommandId

from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from greenmind.greenhouse_config import PlantId
from greenmind.greenhouse_config import Percentage

Provenance = Literal["meteo_simulee", "meteo_historique"]
from greenmind.simulator.engine import SimulationSnapshot


class WireModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, allow_inf_nan=False)
    schema_version: Annotated[int, Field(ge=3, le=3)] = 3


class TelemetryV3(WireModel):
    event_id: EventId
    simulation: SimulationId
    plant_id: PlantId
    observed_at: BelgianTime
    simulated_at: BelgianTime
    emitted_at: BelgianInstant
    cycle: Annotated[int, Field(ge=1)] = 1
    heure_virtuelle: Annotated[int, Field(ge=0, le=24)]
    current_state: Annotated[int, Field(ge=0)]
    paused: bool
    day_complete: bool
    air_temperature_c: float
    air_humidity_pct: Percentage
    soil_moisture_pct: Percentage
    arroseur_active: bool
    provenance: Provenance
    measurement_origin: Literal["initial", "calcul_horaire", "modification_manuelle", "arrosage", "signal_presence", "jour_suivant"]

    @field_validator("observed_at", "simulated_at", "emitted_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def coherent_state(self) -> Self:
        if self.current_state < self.heure_virtuelle:
            raise ValueError("La révision ne peut pas précéder le pas simulé.")
        if self.day_complete != (self.heure_virtuelle == 24) or (self.day_complete and not self.paused):
            raise ValueError("La fin de journée doit correspondre au pas 24 en pause.")
        offset = timedelta(hours=1 if self.heure_virtuelle else 0)
        if self.simulated_at != self.observed_at + offset:
            raise ValueError("L'heure virtuelle doit correspondre à l'intervalle météo appliqué.")
        if self.measurement_origin == "initial" and (self.cycle != 1 or self.heure_virtuelle or self.current_state):
            raise ValueError("Une mesure initiale doit être au pas et à la révision zéro.")
        return self


class SimulationControl(WireModel):
    control_id: ControlId
    simulation: SimulationId
    expected_state: Annotated[int, Field(ge=0)]
    action: SimulationAction
    requested_at: BelgianInstant
    expires_at: BelgianInstant
    plant_id: PlantId | None = None
    moist_request_pct: Percentage | None = None

    @field_validator("requested_at", "expires_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def validate_arguments(self) -> Self:
        if not timedelta(0) < self.expires_at - self.requested_at <= timedelta(seconds=60):
            raise ValueError("Un contrôle doit expirer entre 0 et 60 secondes après sa demande.")
        if self.action == "modifier_humidite_sol":
            if self.plant_id is None or self.moist_request_pct is None:
                raise ValueError("Le bac et la valeur sont obligatoires pour imposer l'humidité.")
        elif self.plant_id is not None or self.moist_request_pct is not None:
            raise ValueError("Cette action n'accepte ni bac ni valeur.")
        return self


class SimulationEvent(WireModel):
    event_id: EventId
    simulation: SimulationId
    control_id: ControlId | None = None
    status: Literal["etat_actuel", "appliqué", "refusé"]
    current_state: Annotated[int, Field(ge=0)]
    cycle: Annotated[int, Field(ge=1)] = 1
    heure_virtuelle: Annotated[int, Field(ge=0, le=24)]
    simulated_at: BelgianTime
    emitted_at: BelgianInstant
    paused: bool
    day_complete: bool
    reason: str


def parse_v3(model, payload):
    try:
        # Le numéro doit être explicite sur le réseau, malgré la valeur par défaut Python.
        result = model.model_validate_json(payload)
        if "schema_version" not in result.model_fields_set:
            raise ValueError("Le champ schema_version est obligatoire sur le réseau.")
        return result
    except ValidationError as error:
        fields = sorted({".".join(map(str, item["loc"])) or "JSON" for item in error.errors()})
        raise ValueError("Message v3 invalide. Vérifier : " + ", ".join(fields) + ".") from error


def telemetry_for_snapshot(snapshot: SimulationSnapshot, origin: str) -> tuple[TelemetryV3, ...]:
    """Trois événements corrélés au même état ; chaque republication est nouvelle."""
    now = datetime.now(timezone.utc)
    return tuple(TelemetryV3(
        event_id=next_id("event"), simulation=snapshot.simulation, plant_id=plant_id,
        observed_at=snapshot.weather.observed_at, simulated_at=snapshot.simulated_at,
        emitted_at=now, cycle=snapshot.cycle, heure_virtuelle=snapshot.heure_virtuelle,
        current_state=snapshot.current_state, paused=snapshot.paused,
        day_complete=snapshot.day_complete, air_temperature_c=snapshot.weather.air_temperature_c,
        air_humidity_pct=snapshot.weather.air_humidity_pct, soil_moisture_pct=value,
        arroseur_active=False, provenance=snapshot.weather.provenance, measurement_origin=origin,
    ) for plant_id, value in snapshot.soil_values)


class WateringCommand(WireModel):
    command_id: CommandId
    simulation: SimulationId
    plant_id: PlantId
    arroseur_id: str
    watering_duration_s: Annotated[float, Field(gt=0, le=10)]
    expected_state: Annotated[int, Field(ge=0)]
    requested_at: BelgianInstant
    expires_at: BelgianInstant

    @field_validator('requested_at', 'expires_at')
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        return value.astimezone(timezone.utc)

    @model_validator(mode='after')
    def coherent_command(self) -> Self:
        from greenmind.greenhouse_config import IDENTITIES
        if self.arroseur_id != IDENTITIES[self.plant_id][1]:
            raise ValueError("L'arroseur doit correspondre au bac ciblé.")
        if not timedelta(0) < self.expires_at - self.requested_at <= timedelta(seconds=60):
            raise ValueError("La commande doit expirer dans les 60 secondes réelles.")
        return self


class WateringEvent(WireModel):
    event_id: EventId
    command_id: CommandId
    simulation: SimulationId
    plant_id: PlantId
    arroseur_id: str
    status: Literal['appliqué', 'refusé']
    resulting_state: Annotated[int, Field(ge=0)]
    simulated_at: BelgianTime
    emitted_at: BelgianInstant
    moist_after_pct: Percentage
    watering_applied_duration_s: Annotated[float, Field(ge=0, le=10)]
    reason: str

    @field_validator('simulated_at', 'emitted_at')
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        return value.astimezone(timezone.utc)

    @model_validator(mode='after')
    def coherent_result(self) -> Self:
        from greenmind.greenhouse_config import IDENTITIES
        if self.arroseur_id != IDENTITIES[self.plant_id][1]:
            raise ValueError("L'arroseur doit correspondre au bac ciblé.")
        if (self.status == 'appliqué') != (self.watering_applied_duration_s > 0):
            raise ValueError("Seul un arrosage appliqué possède une durée positive.")
        return self
