"""Modèles Pydantic pour l'API REST GreenMind (/api/v1)."""

from typing import Annotated, Any, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class HealthResponse(ApiModel):
    status: Literal["ok", "degraded"]
    run_id: str | None
    database_connected: bool
    mqtt_connected: bool
    demo_mode: bool = True


class AlertResponse(ApiModel):
    alert_id: str
    run_id: str
    plant_id: str
    status: Literal["OPEN", "CLOSED"]
    opened_at: str
    closed_at: str | None = None
    trigger_moisture_pct: float
    resolved_moisture_pct: float | None = None


class PlantSummary(ApiModel):
    plant_id: str
    bed_id: str
    actuator_id: str
    display_name: str
    soil_moisture_sim_pct: float | None = None
    air_temperature_c: float | None = None
    air_humidity_pct: float | None = None
    observed_at: str | None = None
    simulated_at: str | None = None
    simulated_tick: int | None = None
    state_revision: int | None = None
    paused: bool | None = None
    has_active_alert: bool = False
    active_alert: AlertResponse | None = None


class PlantDetail(PlantSummary):
    low_threshold_sim_pct: float
    rearm_threshold_sim_pct: float
    high_threshold_sim_pct: float
    target_soil_moisture_sim_pct: float
    base_evaporation_per_hour: float
    reference_temperature_c: float
    temperature_factor_per_c: float
    irrigation_gain_per_sim_s: float
    max_watering_duration_sim_s: float
    watering_cooldown_real_s: float


class MeasurementItem(ApiModel):
    event_id: str
    plant_id: str
    simulated_at: str
    emitted_at: str
    received_at: str
    simulated_tick: int
    state_revision: int
    soil_moisture_sim_pct: float
    air_temperature_c: float
    air_humidity_pct: float
    pump_active: bool
    measurement_origin: str


class EventItem(ApiModel):
    sequence: int
    event_id: str
    run_id: str
    plant_id: str | None = None
    created_at: str
    simulated_at: str | None = None
    event_type: str
    summary: str
    details: dict[str, Any] = Field(default_factory=dict)


class SimulationStateResponse(ApiModel):
    run_id: str | None = None
    simulated_tick: int = 0
    state_revision: int = 0
    simulated_at: str | None = None
    paused: bool = True
    completed: bool = False
    scenario: str = "demo_greenhouse_day"
    presence: bool = False


class ControlRequest(ApiModel):
    action: Literal["PAUSE", "RESUME", "ADVANCE", "SET_SOIL_MOISTURE"]
    expected_revision: Annotated[int, Field(ge=0)]
    plant_id: Literal["basilic_01", "thym_01", "romarin_01"] | None = None
    value: Annotated[float, Field(ge=0, le=100)] | None = None
    control_id: UUID | None = None


class ControlAcceptedResponse(ApiModel):
    control_id: str
    status: Literal["PENDING"] = "PENDING"
    action: str
    expected_revision: int
    message: str = "Commande de simulation acceptée pour publication."


class ControlStatusResponse(ApiModel):
    control_id: str
    status: Literal["PENDING", "APPLIED", "REJECTED"]
    state_revision: int | None = None
    simulated_tick: int | None = None
    simulated_at: str | None = None
    reason: str | None = None
