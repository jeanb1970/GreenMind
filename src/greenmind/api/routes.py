"""Routes REST FastAPI (/api/v1) de la serre GreenMind."""

from datetime import datetime, timedelta, timezone
import json
import socket
from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, HTTPException, Query, status
from greenmind.api.dependencies import get_config, get_db, get_publisher, MqttPublisher
from greenmind.api.schemas import (
    AlertResponse,
    ControlAcceptedResponse,
    ControlRequest,
    ControlStatusResponse,
    EventItem,
    HealthResponse,
    MeasurementItem,
    PlantDetail,
    PlantSummary,
    SimulationStateResponse,
)
from greenmind.db.readings import (
    active_alert,
    get_control_event,
    latest_reading,
    latest_run_id,
    list_events,
    recent_readings,
    reserve_control,
)
from greenmind.greenhouse_config import GreenhouseConfig
from greenmind.schemas import SimulationControl

router = APIRouter(prefix="/api/v1", tags=["Serre GreenMind"])


@router.get("/health", response_model=HealthResponse, tags=["Santé"])
def health_check(
    db=Depends(get_db),
    publisher: MqttPublisher = Depends(get_publisher),
):
    """Vérifie la santé des services, l'accès SQLite et la session active."""
    db_ok = False
    try:
        with db.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
            db_ok = True
    except Exception:
        db_ok = False

    mqtt_ok = False
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1.0)
        result = sock.connect_ex((publisher.host, publisher.port))
        mqtt_ok = (result == 0)
        sock.close()
    except Exception:
        mqtt_ok = False

    run_id = latest_run_id(db) if db_ok else None
    overall_status = "ok" if (db_ok and mqtt_ok) else "degraded"

    return HealthResponse(
        status=overall_status,
        run_id=run_id,
        database_connected=db_ok,
        mqtt_connected=mqtt_ok,
        demo_mode=True,
    )


@router.get("/plants", response_model=list[PlantSummary])
def get_plants(
    db=Depends(get_db),
    config: GreenhouseConfig = Depends(get_config),
):
    """Retourne la synthèse des trois bacs et leur dernière mesure."""
    run_id = latest_run_id(db)
    results = []

    for plant_cfg in config.plants:
        reading = latest_reading(db, run_id, plant_cfg.plant_id) if run_id else None
        alert = active_alert(db, run_id, plant_cfg.plant_id) if run_id else None

        alert_dto = None
        if alert is not None:
            alert_dto = AlertResponse(
                alert_id=alert.alert_id,
                run_id=alert.run_id,
                plant_id=alert.plant_id,
                status=alert.status,
                opened_at=alert.opened_at,
                closed_at=alert.closed_at,
                trigger_moisture_pct=alert.trigger_moisture_pct,
                resolved_moisture_pct=alert.resolved_moisture_pct,
            )

        results.append(PlantSummary(
            plant_id=plant_cfg.plant_id,
            bed_id=plant_cfg.bed_id,
            actuator_id=plant_cfg.actuator_id,
            display_name=plant_cfg.display_name,
            soil_moisture_sim_pct=reading.soil_moisture_sim_pct if reading else None,
            air_temperature_c=reading.air_temperature_c if reading else None,
            air_humidity_pct=reading.air_humidity_pct if reading else None,
            observed_at=reading.observed_at if reading else None,
            simulated_at=reading.simulated_at if reading else None,
            simulated_tick=reading.simulated_tick if reading else None,
            state_revision=reading.state_revision if reading else None,
            paused=reading.paused if reading else None,
            has_active_alert=alert is not None,
            active_alert=alert_dto,
        ))

    return results


@router.get("/plants/{plant_id}", response_model=PlantDetail)
def get_plant_detail(
    plant_id: str,
    db=Depends(get_db),
    config: GreenhouseConfig = Depends(get_config),
):
    """Retourne le profil détaillé, seuils et état d'un bac spécifique."""
    try:
        plant_cfg = config.get_plant(plant_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Le bac '{plant_id}' est inconnu dans la serre.",
        )

    run_id = latest_run_id(db)
    reading = latest_reading(db, run_id, plant_id) if run_id else None
    alert = active_alert(db, run_id, plant_id) if run_id else None

    alert_dto = None
    if alert is not None:
        alert_dto = AlertResponse(
            alert_id=alert.alert_id,
            run_id=alert.run_id,
            plant_id=alert.plant_id,
            status=alert.status,
            opened_at=alert.opened_at,
            closed_at=alert.closed_at,
            trigger_moisture_pct=alert.trigger_moisture_pct,
            resolved_moisture_pct=alert.resolved_moisture_pct,
        )

    return PlantDetail(
        plant_id=plant_cfg.plant_id,
        bed_id=plant_cfg.bed_id,
        actuator_id=plant_cfg.actuator_id,
        display_name=plant_cfg.display_name,
        soil_moisture_sim_pct=reading.soil_moisture_sim_pct if reading else None,
        air_temperature_c=reading.air_temperature_c if reading else None,
        air_humidity_pct=reading.air_humidity_pct if reading else None,
        observed_at=reading.observed_at if reading else None,
        simulated_at=reading.simulated_at if reading else None,
        simulated_tick=reading.simulated_tick if reading else None,
        state_revision=reading.state_revision if reading else None,
        paused=reading.paused if reading else None,
        has_active_alert=alert is not None,
        active_alert=alert_dto,
        low_threshold_sim_pct=plant_cfg.low_threshold_sim_pct,
        rearm_threshold_sim_pct=plant_cfg.rearm_threshold_sim_pct,
        high_threshold_sim_pct=plant_cfg.high_threshold_sim_pct,
        target_soil_moisture_sim_pct=plant_cfg.target_soil_moisture_sim_pct,
        base_evaporation_per_hour=plant_cfg.base_evaporation_per_hour,
        reference_temperature_c=plant_cfg.reference_temperature_c,
        temperature_factor_per_c=plant_cfg.temperature_factor_per_c,
        irrigation_gain_per_sim_s=plant_cfg.irrigation_gain_per_sim_s,
        max_watering_duration_sim_s=plant_cfg.max_watering_duration_sim_s,
        watering_cooldown_real_s=plant_cfg.watering_cooldown_real_s,
    )


@router.get("/plants/{plant_id}/measurements", response_model=list[MeasurementItem])
def get_plant_measurements(
    plant_id: str,
    limit: int = Query(24, ge=1, le=100),
    db=Depends(get_db),
    config: GreenhouseConfig = Depends(get_config),
):
    """Retourne les mesures récentes d'un bac pour l'exécution courante."""
    try:
        config.get_plant(plant_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Le bac '{plant_id}' est inconnu.",
        )

    run_id = latest_run_id(db)
    if not run_id:
        return []

    readings = recent_readings(db, run_id, plant_id, limit=limit)
    return [
        MeasurementItem(
            event_id=r.event_id,
            plant_id=r.plant_id,
            simulated_at=r.simulated_at,
            emitted_at=r.emitted_at,
            received_at=r.received_at,
            simulated_tick=r.simulated_tick,
            state_revision=r.state_revision,
            soil_moisture_sim_pct=r.soil_moisture_sim_pct,
            air_temperature_c=r.air_temperature_c,
            air_humidity_pct=r.air_humidity_pct,
            pump_active=r.pump_active,
            measurement_origin=r.measurement_origin,
        )
        for r in readings
    ]


@router.get("/events", response_model=list[EventItem])
def get_events(
    plant_id: str | None = Query(None),
    limit: int = Query(100, ge=1, le=100),
    db=Depends(get_db),
    config: GreenhouseConfig = Depends(get_config),
):
    """100 derniers événements de la session courante, filtrable par bac."""
    if plant_id is not None:
        try:
            config.get_plant(plant_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Le bac '{plant_id}' est inconnu.",
            )

    run_id = latest_run_id(db)
    if not run_id:
        return []

    rows = list_events(db, run_id, plant_id=plant_id, limit=limit)
    result = []
    for r in rows:
        try:
            details = json.loads(r.details_json) if r.details_json else {}
        except Exception:
            details = {}
        result.append(EventItem(
            sequence=r.sequence,
            event_id=r.event_id,
            run_id=r.run_id,
            plant_id=r.plant_id,
            created_at=r.created_at,
            simulated_at=r.simulated_at,
            event_type=r.event_type,
            summary=r.summary,
            details=details,
        ))
    return result


@router.get("/simulation", response_model=SimulationStateResponse)
def get_simulation_state(
    db=Depends(get_db),
):
    """Retourne l'état courant de l'horloge et de la simulation."""
    run_id = latest_run_id(db)
    if not run_id:
        return SimulationStateResponse()

    # Prendre la lecture la plus récente parmi les bacs
    sample = latest_reading(db, run_id, "basilic_01")
    if sample is None:
        return SimulationStateResponse(run_id=run_id)

    # Vérification de présence (message émis dans les 10 dernières secondes)
    presence = False
    try:
        emitted = datetime.fromisoformat(sample.emitted_at.replace("Z", "+00:00"))
        if datetime.now(timezone.utc) - emitted < timedelta(seconds=10):
            presence = True
    except Exception:
        presence = False

    return SimulationStateResponse(
        run_id=run_id,
        simulated_tick=sample.simulated_tick,
        state_revision=sample.state_revision,
        simulated_at=sample.simulated_at,
        paused=sample.paused,
        completed=sample.completed,
        scenario="demo_greenhouse_day",
        presence=presence,
    )


@router.post(
    "/simulation/controls",
    response_model=ControlAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def post_simulation_control(
    payload: ControlRequest,
    db=Depends(get_db),
    publisher: MqttPublisher = Depends(get_publisher),
):
    """Émet asynchroniquement une commande de simulation vers MQTT."""
    run_id_str = latest_run_id(db)
    if not run_id_str:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Aucune session de simulation active.",
        )

    run_id = UUID(run_id_str)

    control_id = payload.control_id or uuid4()
    now = datetime.now(timezone.utc)

    try:
        command = SimulationControl(
            control_id=control_id,
            run_id=run_id,
            expected_revision=payload.expected_revision,
            action=payload.action,
            requested_at=now,
            expires_at=now + timedelta(seconds=30),
            plant_id=payload.plant_id,
            value=payload.value,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=422,
            detail=f"Commande invalide : {error}.",
        ) from error

    try:
        command = reserve_control(db, command)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error

    # Après un acquittement, retourner la même acceptation sans republier.
    # Sinon, republier le message exact, y compris ses dates d'expiration.
    if get_control_event(db, command.control_id) is None:
        publisher.publish_control(command.model_dump_json())

    return ControlAcceptedResponse(
        control_id=str(control_id),
        status="PENDING",
        action=payload.action,
        expected_revision=payload.expected_revision,
        message=f"Commande {payload.action} acceptée ; résultat disponible via son identifiant de suivi.",
    )


@router.get("/simulation/controls/{control_id}", response_model=ControlStatusResponse)
def get_control_status(
    control_id: UUID,
    db=Depends(get_db),
):
    """Retourne l'état d'exécution corrélé d'un contrôle de simulation."""
    row = get_control_event(db, control_id)
    if row is None:
        return ControlStatusResponse(
            control_id=str(control_id),
            status="PENDING",
            reason="La commande est en cours de traitement ou en attente d'acquittement.",
        )

    try:
        data = json.loads(row.payload)
        return ControlStatusResponse(
            control_id=str(control_id),
            status=data.get("status", "APPLIED"),
            state_revision=data.get("state_revision"),
            simulated_tick=data.get("simulated_tick"),
            simulated_at=data.get("simulated_at"),
            reason=data.get("reason"),
        )
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Impossible de lire le résultat du contrôle : {error}.",
        ) from error
