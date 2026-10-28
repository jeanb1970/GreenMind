"""Modèles Pydantic pour l'API REST GreenMind (/api/v1)."""
from greenmind.identifiers import ControlId

from typing import Annotated, Any, Literal
from pydantic import BaseModel, ConfigDict, Field


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class HealthResponse(ApiModel):
    status: Literal["ok", "dégradé"]
    simulation: str | None
    database_connected: bool
    mqtt_connected: bool
    simulation_mode: bool = True


class AlertResponse(ApiModel):
    alert_id: str
    simulation: str
    plant_id: str
    status: Literal["ouverte", "clôturée"]
    opened_at: str
    closed_at: str | None = None
    moist_trigger_pct: float
    moist_resolved_pct: float | None = None


class PlantSummary(ApiModel):
    plant_id: str
    bed_id: str
    arroseur_id: str
    display_name: str
    soil_moisture_pct: float | None = None
    air_temperature_c: float | None = None
    air_humidity_pct: float | None = None
    observed_at: str | None = None
    simulated_at: str | None = None
    heure_virtuelle: int | None = None
    current_state: int | None = None
    paused: bool | None = None
    has_active_alert: bool = False
    active_alert: AlertResponse | None = None


class PlantDetail(PlantSummary):
    moist_low_pct: float
    moist_rearm_pct: float
    moist_high_pct: float
    moist_target_pct: float
    evaporation_pct_per_hour: float
    reference_temperature_c: float
    temperature_factor_per_c: float
    watering_gain_pct_per_s: float
    watering_max_duration_s: float
    watering_rest_s: float


class MeasurementItem(ApiModel):
    event_id: str
    plant_id: str
    simulated_at: str
    emitted_at: str
    received_at: str
    heure_virtuelle: int
    current_state: int
    soil_moisture_pct: float
    air_temperature_c: float
    air_humidity_pct: float
    arroseur_active: bool
    measurement_origin: str


class EventItem(ApiModel):
    sequence: int
    event_id: str
    simulation: str
    plant_id: str | None = None
    created_at: str
    simulated_at: str | None = None
    event_type: str
    summary: str
    details: dict[str, Any] = Field(default_factory=dict)


class SimulationStateResponse(ApiModel):
    simulation: str | None = None
    heure_virtuelle: int = 0
    current_state: int = 0
    simulated_at: str | None = None
    paused: bool = True
    day_complete: bool = False
    scenario: str = "journee_serre"
    presence: bool = False


class ControlRequest(ApiModel):
    action: Literal["pause", "reprendre", "avancer_1_heure", "modifier_humidite_sol"]
    expected_state: Annotated[int, Field(ge=0)]
    plant_id: Literal["basilic", "thym", "romarin"] | None = None
    moist_request_pct: Annotated[float, Field(ge=0, le=100)] | None = None
    control_id: ControlId | None = None


class ControlAcceptedResponse(ApiModel):
    control_id: str
    status: Literal["en_attente"] = "en_attente"
    action: str
    expected_state: int
    message: str = "Commande de simulation acceptée pour publication."


class ControlStatusResponse(ApiModel):
    control_id: str
    status: Literal["en_attente", "appliqué", "refusé"]
    current_state: int | None = None
    heure_virtuelle: int | None = None
    simulated_at: str | None = None
    reason: str | None = None
