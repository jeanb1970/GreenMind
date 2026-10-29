"""Routes REST FastAPI (/api/v1) de la serre GreenMind."""
from greenmind.simulation_rules import PRESENCE_TTL_SECONDS, MAX_MEASUREMENTS
from greenmind.time_formats import parse_local
from greenmind.identifiers import next_id, ControlId

from datetime import datetime, timedelta, timezone
import json
import socket
from fastapi import APIRouter, Depends, HTTPException, Query, status
from greenmind.api.dependencies import (
    get_config, get_db, get_publisher, get_simulation_mode, require_simulation_mode, MqttPublisher,
)
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
    latest_simulation,
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
    simulation_mode: bool = Depends(get_simulation_mode),
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

    simulation = latest_simulation(db) if db_ok else None
    overall_status = "ok" if (db_ok and mqtt_ok) else "dégradé"

    return HealthResponse(
        status=overall_status,
        simulation=simulation,
        database_connected=db_ok,
        mqtt_connected=mqtt_ok,
        simulation_mode=simulation_mode,
    )


@router.get("/plants", response_model=list[PlantSummary])
def get_plants(
    db=Depends(get_db),
    config: GreenhouseConfig = Depends(get_config),
):
    """Retourne la synthèse des trois bacs et leur dernière mesure."""
    simulation = latest_simulation(db)
    results = []

    for plant_cfg in config.plants:
        reading = latest_reading(db, simulation, plant_cfg.plant_id) if simulation else None
        alert = active_alert(db, simulation, plant_cfg.plant_id) if simulation else None

        alert_dto = None
        if alert is not None:
            alert_dto = AlertResponse(
                alert_id=alert.alert_id,
                simulation=alert.simulation,
                plant_id=alert.plant_id,
                status=alert.status,
                opened_at=alert.opened_at,
                closed_at=alert.closed_at,
                moist_trigger_pct=alert.moist_trigger_pct,
                moist_resolved_pct=alert.moist_resolved_pct,
            )

        results.append(PlantSummary(
            plant_id=plant_cfg.plant_id,
            bed_id=plant_cfg.bed_id,
            arroseur_id=plant_cfg.arroseur_id,
            display_name=plant_cfg.display_name,
            moist_low_pct=plant_cfg.moist_low_pct,
            moist_rearm_pct=plant_cfg.moist_rearm_pct,
            moist_high_pct=plant_cfg.moist_high_pct,
            moist_target_pct=plant_cfg.moist_target_pct,
            arroseur_active=reading.arroseur_active if reading else None,
            soil_moisture_pct=reading.soil_moisture_pct if reading else None,
            air_temperature_c=reading.air_temperature_c if reading else None,
            air_humidity_pct=reading.air_humidity_pct if reading else None,
            observed_at=reading.observed_at if reading else None,
            simulated_at=reading.simulated_at if reading else None,
            heure_virtuelle=reading.heure_virtuelle if reading else None,
            current_state=reading.current_state if reading else None,
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

    simulation = latest_simulation(db)
    reading = latest_reading(db, simulation, plant_id) if simulation else None
    alert = active_alert(db, simulation, plant_id) if simulation else None

    alert_dto = None
    if alert is not None:
        alert_dto = AlertResponse(
            alert_id=alert.alert_id,
            simulation=alert.simulation,
            plant_id=alert.plant_id,
            status=alert.status,
            opened_at=alert.opened_at,
            closed_at=alert.closed_at,
            moist_trigger_pct=alert.moist_trigger_pct,
            moist_resolved_pct=alert.moist_resolved_pct,
        )

    return PlantDetail(
        plant_id=plant_cfg.plant_id,
        bed_id=plant_cfg.bed_id,
        arroseur_id=plant_cfg.arroseur_id,
        display_name=plant_cfg.display_name,
        arroseur_active=reading.arroseur_active if reading else None,
        soil_moisture_pct=reading.soil_moisture_pct if reading else None,
        air_temperature_c=reading.air_temperature_c if reading else None,
        air_humidity_pct=reading.air_humidity_pct if reading else None,
        observed_at=reading.observed_at if reading else None,
        simulated_at=reading.simulated_at if reading else None,
        heure_virtuelle=reading.heure_virtuelle if reading else None,
        current_state=reading.current_state if reading else None,
        paused=reading.paused if reading else None,
        has_active_alert=alert is not None,
        active_alert=alert_dto,
        moist_low_pct=plant_cfg.moist_low_pct,
        moist_rearm_pct=plant_cfg.moist_rearm_pct,
        moist_high_pct=plant_cfg.moist_high_pct,
        moist_target_pct=plant_cfg.moist_target_pct,
        evaporation_pct_per_hour=plant_cfg.evaporation_pct_per_hour,
        reference_temperature_c=plant_cfg.reference_temperature_c,
        temperature_factor_per_c=plant_cfg.temperature_factor_per_c,
        watering_gain_pct_per_s=plant_cfg.watering_gain_pct_per_s,
        watering_max_duration_s=plant_cfg.watering_max_duration_s,
        watering_rest_s=plant_cfg.watering_rest_s,
    )


@router.get("/plants/{plant_id}/measurements", response_model=list[MeasurementItem])
def get_plant_measurements(
    plant_id: str,
    limit: int = Query(24, ge=1, le=MAX_MEASUREMENTS),
    include_presence: bool = Query(True),
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

    simulation = latest_simulation(db)
    if not simulation:
        return []

    readings = recent_readings(db, simulation, plant_id, limit=limit, include_presence=include_presence)
    return [
        MeasurementItem(
            event_id=r.event_id,
            plant_id=r.plant_id,
            simulated_at=r.simulated_at,
            emitted_at=r.emitted_at,
            received_at=r.received_at,
            cycle=r.cycle, heure_virtuelle=r.heure_virtuelle,
            current_state=r.current_state,
            soil_moisture_pct=r.soil_moisture_pct,
            air_temperature_c=r.air_temperature_c,
            air_humidity_pct=r.air_humidity_pct,
            arroseur_active=r.arroseur_active,
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

    simulation = latest_simulation(db)
    if not simulation:
        return []

    rows = list_events(db, simulation, plant_id=plant_id, limit=limit)
    result = []
    for r in rows:
        try:
            details = json.loads(r.details) if r.details else {}
        except Exception:
            details = {}
        result.append(EventItem(
            sequence=r.sequence,
            event_id=r.event_id,
            simulation=r.simulation,
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
    simulation_mode: bool = Depends(get_simulation_mode),
):
    """Retourne l'état courant de l'horloge et de la simulation."""
    simulation = latest_simulation(db)
    if not simulation:
        return SimulationStateResponse(simulation_mode=simulation_mode)

    # Horloge et météo commune issues de la même mesure de référence.
    sample = latest_reading(db, simulation, "basilic")
    if sample is None:
        return SimulationStateResponse(simulation=simulation, simulation_mode=simulation_mode)

    # Vérification de présence (message émis dans les 10 dernières secondes)
    presence = False
    try:
        emitted = parse_local(sample.emitted_at)
        if timedelta(0) <= datetime.now(timezone.utc) - emitted < timedelta(seconds=PRESENCE_TTL_SECONDS):
            presence = True
    except Exception:
        presence = False

    return SimulationStateResponse(
        simulation_mode=simulation_mode,
        simulation=simulation,
        cycle=sample.cycle, heure_virtuelle=sample.heure_virtuelle,
        current_state=sample.current_state,
        simulated_at=sample.simulated_at,
        paused=sample.paused,
        day_complete=sample.day_complete,
        scenario="journee_serre",
        presence=presence,
        air_temperature_c=sample.air_temperature_c,
        air_humidity_pct=sample.air_humidity_pct,
        observed_at=sample.observed_at,
        provenance=sample.provenance,
    )


@router.post(
    "/simulation/controls",
    response_model=ControlAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_simulation_mode)],
)
def post_simulation_control(
    payload: ControlRequest,
    db=Depends(get_db),
    publisher: MqttPublisher = Depends(get_publisher),
):
    """Émet asynchroniquement une commande de simulation vers MQTT."""
    simulation_str = latest_simulation(db)
    if not simulation_str:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Aucune session de simulation active.",
        )

    simulation = simulation_str

    control_id = payload.control_id or next_id("control")
    now = datetime.now(timezone.utc)

    try:
        command = SimulationControl(
            control_id=control_id,
            simulation=simulation,
            expected_state=payload.expected_state,
            action=payload.action,
            requested_at=now,
            expires_at=now + timedelta(seconds=30),
            plant_id=payload.plant_id,
            moist_request_pct=payload.moist_request_pct,
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
        status="en_attente",
        action=payload.action,
        expected_state=payload.expected_state,
        message=f"Commande {payload.action} acceptée ; résultat disponible via son identifiant de suivi.",
    )


@router.get("/simulation/controls/{control_id}", response_model=ControlStatusResponse)
def get_control_status(
    control_id: ControlId,
    db=Depends(get_db),
):
    """Retourne l'état d'exécution corrélé d'un contrôle de simulation."""
    row = get_control_event(db, control_id)
    if row is None:
        return ControlStatusResponse(
            control_id=str(control_id),
            status="en_attente",
            reason="La commande est en cours de traitement ou en attente d'acquittement.",
        )

    try:
        data = json.loads(row.payload)
        return ControlStatusResponse(
            control_id=str(control_id),
            status=data.get("status", "appliqué"),
            current_state=data.get("current_state"),
            heure_virtuelle=data.get("heure_virtuelle"),
            simulated_at=data.get("simulated_at"),
            reason=data.get("reason"),
        )
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Impossible de lire le résultat du contrôle : {error}.",
        ) from error


@router.post('/identifiers/{category}')
def allocate_identifier(category: str):
    """Alloue une clé que le client conserve pour ses nouvelles tentatives."""
    if category not in ('control', 'proposal', 'command'):
        raise HTTPException(status_code=404, detail="Catégorie d'identifiant inconnue.")
    return {'identifier': next_id(category)}
