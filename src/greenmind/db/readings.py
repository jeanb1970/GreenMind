"""Persistance atomique et lecture des mesures, alertes et journal de la serre."""
from greenmind.time_formats import local_text
from greenmind.display import percent
from greenmind.identifiers import next_id
from greenmind.simulation_rules import MAX_MEASUREMENTS, MAX_JOURNAL_EVENTS

from datetime import datetime, timezone
from functools import lru_cache
import json
from pathlib import Path
from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session
from greenmind.db.models import (
    AlertRow,
    GreenhouseEventRow,
    GreenhouseReading,
    SimulationEventRow,
    SimulationRun,
    SimulationControlRow,
    WateringEventRow,
)
from greenmind.domain.alerts import next_dry_alert_state
from greenmind.greenhouse_config import GreenhouseConfig, load_greenhouse_config
from greenmind.schemas import SimulationControl, SimulationEvent, TelemetryV3, WateringEvent

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config/greenhouse.yaml"


@lru_cache(maxsize=1)
def get_default_greenhouse_config() -> GreenhouseConfig:
    return load_greenhouse_config(DEFAULT_CONFIG_PATH)


def instant_text(value: datetime) -> str:
    return local_text(value)


def _handle_telemetry_side_effects(
    session: Session,
    message: TelemetryV3,
    received_at: str,
    config: GreenhouseConfig,
) -> None:
    """Ouvre ou ferme atomiquement l'alerte de sécheresse et alimente le journal."""
    bed = config.get_plant(message.plant_id)
    active = session.scalar(
        select(AlertRow).where(
            AlertRow.simulation == str(message.simulation),
            AlertRow.plant_id == message.plant_id,
            AlertRow.status == "ouverte",
        ).order_by(AlertRow.opened_at.desc()).limit(1)
    )
    is_currently_open = active is not None
    should_be_open = next_dry_alert_state(
        message.soil_moisture_pct,
        alert_open=is_currently_open,
        moist_low_pct=bed.moist_low_pct,
        moist_rearm_pct=bed.moist_rearm_pct,
    )

    if not is_currently_open and should_be_open:
        new_alert_id = next_id("alert")
        session.add(AlertRow(
            alert_id=new_alert_id,
            simulation=str(message.simulation),
            plant_id=message.plant_id,
            status="ouverte",
            opened_at=received_at,
            opening_event_id=str(message.event_id),
            moist_trigger_pct=message.soil_moisture_pct,
        ))
        session.add(GreenhouseEventRow(
            event_id=next_id("event"),
            simulation=str(message.simulation),
            plant_id=message.plant_id,
            created_at=received_at,
            simulated_at=local_text(message.simulated_at, False),
            event_type="alerte_ouverte",
            summary=f"Alerte de sécheresse ouverte sur {bed.display_name} ({percent(message.soil_moisture_pct)} < {percent(bed.moist_low_pct)}).",
            details=json.dumps({
                "alert_id": new_alert_id,
                "plant_id": message.plant_id,
                "moist_trigger_pct": message.soil_moisture_pct,
                "moist_low_pct": bed.moist_low_pct,
            }),
        ))
    elif is_currently_open and not should_be_open and active is not None:
        active.status = "clôturée"
        active.closed_at = received_at
        active.closing_event_id = str(message.event_id)
        active.moist_resolved_pct = message.soil_moisture_pct
        session.add(GreenhouseEventRow(
            event_id=next_id("event"),
            simulation=str(message.simulation),
            plant_id=message.plant_id,
            created_at=received_at,
            simulated_at=local_text(message.simulated_at, False),
            event_type="alerte_clôturée",
            summary=f"Alerte de sécheresse levée sur {bed.display_name} ({percent(message.soil_moisture_pct)} > {percent(bed.moist_rearm_pct)}).",
            details=json.dumps({
                "alert_id": active.alert_id,
                "plant_id": message.plant_id,
                "moist_resolved_pct": message.soil_moisture_pct,
                "moist_rearm_pct": bed.moist_rearm_pct,
            }),
        ))

    if message.measurement_origin == "modification_manuelle":
        previous = session.scalar(
            select(GreenhouseReading.soil_moisture_pct).where(
                GreenhouseReading.simulation == str(message.simulation),
                GreenhouseReading.plant_id == message.plant_id,
                GreenhouseReading.event_id != str(message.event_id),
            ).order_by(
                GreenhouseReading.current_state.desc(),
                GreenhouseReading.emitted_at.desc(),
                func.length(GreenhouseReading.event_id).desc(),
                GreenhouseReading.event_id.desc(),
            ).limit(1)
        )
        session.add(GreenhouseEventRow(
            event_id=next_id("event"),
            simulation=str(message.simulation),
            plant_id=message.plant_id,
            created_at=received_at,
            simulated_at=local_text(message.simulated_at, False),
            event_type="modification_manuelle",
            summary=f"Humidité imposée à {percent(message.soil_moisture_pct)} sur {bed.display_name}.",
            details=json.dumps({
                "plant_id": message.plant_id,
                "moist_before_pct": previous,
                "moist_after_pct": message.soil_moisture_pct,
                "soil_moisture_pct": message.soil_moisture_pct,
            }),
        ))


def _handle_simulation_event_side_effects(
    session: Session,
    message: SimulationEvent,
    received_at: str,
) -> None:
    if message.control_id is not None:
        session.add(GreenhouseEventRow(
            event_id=next_id("event"),
            simulation=str(message.simulation),
            plant_id=None,
            created_at=received_at,
            simulated_at=local_text(message.simulated_at, False),
            event_type=f"contrôle_{message.status}",
            summary=message.reason,
            details=json.dumps({
                "control_id": str(message.control_id),
                "status": message.status,
                "current_state": message.current_state,
                "reason": message.reason,
            }),
        ))


def save_message(
    engine,
    message: TelemetryV3 | SimulationEvent | WateringEvent,
    *,
    config: GreenhouseConfig | None = None,
) -> bool:
    """Enregistre le message et applique les effets d'alerte et de journal de manière atomique."""
    received_at = instant_text(datetime.now(timezone.utc))
    if isinstance(message, TelemetryV3):
        model = GreenhouseReading
        values = message.model_dump()
        for key in ("event_id", "simulation"):
            values[key] = str(values[key])
        for key in ("observed_at", "simulated_at", "emitted_at"):
            values[key] = local_text(values[key], precise=(key == "emitted_at"))
        values["received_at"] = received_at
    elif isinstance(message, WateringEvent):
        model = WateringEventRow
        values = dict(event_id=str(message.event_id), simulation=str(message.simulation),
                      command_id=str(message.command_id), received_at=received_at,
                      payload=message.model_dump_json())
    else:
        model = SimulationEventRow
        values = dict(event_id=str(message.event_id), simulation=str(message.simulation),
                      control_id=str(message.control_id) if message.control_id else None,
                      received_at=received_at, payload=message.model_dump_json())

    active_config = config or get_default_greenhouse_config()

    with Session(engine) as session, session.begin():
        session.execute(insert(SimulationRun).values(
            simulation=str(message.simulation), first_received_at=received_at,
        ).on_conflict_do_nothing(index_elements=["simulation"]))

        inserted = session.scalar(insert(model).values(**values)
                                  .on_conflict_do_nothing(index_elements=["event_id"])
                                  .returning(model.event_id))

        if inserted is not None:
            if isinstance(message, TelemetryV3):
                # Conserver les mesures tardives dans l'historique sans rejouer
                # les transitions d'alerte ni les forçages d'un état dépassé.
                current_id = session.scalar(select(GreenhouseReading.event_id).where(
                    GreenhouseReading.simulation == str(message.simulation),
                    GreenhouseReading.plant_id == message.plant_id,
                ).order_by(GreenhouseReading.current_state.desc(),
                           GreenhouseReading.emitted_at.desc(),
                           func.length(GreenhouseReading.event_id).desc(), GreenhouseReading.event_id.desc()).limit(1))
                if current_id == str(message.event_id):
                    _handle_telemetry_side_effects(session, message, received_at, active_config)
            elif isinstance(message, WateringEvent):
                from greenmind.db.arrosage import record_watering_event
                record_watering_event(session, message)
            else:
                _handle_simulation_event_side_effects(session, message, received_at)

    return inserted is not None


def latest_reading(engine, simulation: str, plant_id: str) -> GreenhouseReading | None:
    """Une mesure tardive d'une ancienne révision ne remplace jamais l'état actuel."""
    with Session(engine) as session:
        return session.scalar(select(GreenhouseReading).where(
            GreenhouseReading.simulation == str(simulation), GreenhouseReading.plant_id == plant_id,
        ).order_by(GreenhouseReading.current_state.desc(),
                   GreenhouseReading.emitted_at.desc(), func.length(GreenhouseReading.event_id).desc(), GreenhouseReading.event_id.desc()).limit(1))


def reserve_control(engine, command: SimulationControl) -> SimulationControl:
    """Réserve une clé atomiquement ; un rejeu conserve le message original.

    L'INSERT prend le verrou d'écriture SQLite avant la vérification de révision.
    Les requêtes concurrentes et les redémarrages utilisent ainsi le même contrat.
    """
    with Session(engine) as session, session.begin():
        inserted = session.scalar(insert(SimulationControlRow).values(
            control_id=str(command.control_id), simulation=str(command.simulation),
            payload=command.model_dump_json(),
        ).on_conflict_do_nothing(index_elements=["control_id"])
          .returning(SimulationControlRow.control_id))
        if inserted is None:
            row = session.get(SimulationControlRow, str(command.control_id))
            if row is None:
                raise RuntimeError("Impossible de retrouver la commande réservée en base.")
            original = SimulationControl.model_validate_json(row.payload)
            fields = ("action", "expected_state", "plant_id", "moist_request_pct")
            if any(getattr(original, key) != getattr(command, key) for key in fields):
                raise ValueError("Identifiant de contrôle réutilisé avec un contenu différent.")
            return original

        from greenmind.db.arrosage import ensure_watering_idle
        ensure_watering_idle(session, str(command.simulation))

        sample = session.scalar(select(GreenhouseReading).where(
            GreenhouseReading.simulation == str(command.simulation),
        ).order_by(GreenhouseReading.current_state.desc(),
                   GreenhouseReading.emitted_at.desc()).limit(1))
        if sample is None or sample.current_state != command.expected_state:
            raise ValueError("Conflit de révision d'état : la révision attendue n'est plus courante.")
        return command


def active_alert(engine, simulation: str, plant_id: str) -> AlertRow | None:
    """Retourne l'alerte ouverte pour un bac dans la session courante."""
    with Session(engine) as session:
        return session.scalar(select(AlertRow).where(
            AlertRow.simulation == str(simulation),
            AlertRow.plant_id == plant_id,
            AlertRow.status == "ouverte",
        ).order_by(AlertRow.opened_at.desc()).limit(1))


def list_alerts(engine, simulation: str, plant_id: str | None = None) -> list[AlertRow]:
    """Retourne l'historique des alertes pour la session, optionnellement filtré par bac."""
    with Session(engine) as session:
        query = select(AlertRow).where(AlertRow.simulation == str(simulation))
        if plant_id is not None:
            query = query.where(AlertRow.plant_id == plant_id)
        return list(session.scalars(query.order_by(AlertRow.opened_at.desc())))


def list_events(
    engine,
    simulation: str,
    plant_id: str | None = None,
    limit: int = 100,
) -> list[GreenhouseEventRow]:
    """100 derniers événements de la session courante, avec filtre bac optionnel."""
    server_limit = min(max(1, limit), MAX_JOURNAL_EVENTS)
    with Session(engine) as session:
        query = select(GreenhouseEventRow).where(GreenhouseEventRow.simulation == str(simulation))
        if plant_id is not None:
            query = query.where(GreenhouseEventRow.plant_id == plant_id)
        return list(session.scalars(query.order_by(GreenhouseEventRow.sequence.desc()).limit(server_limit)))


def recent_readings(
    engine,
    simulation: str,
    plant_id: str,
    limit: int = 24,
    *,
    include_presence: bool = True,
) -> list[GreenhouseReading]:
    """Mesures récentes d'un bac pour l'exécution courante, limite serveur imposée."""
    server_limit = min(max(1, limit), MAX_MEASUREMENTS)
    with Session(engine) as session:
        query = select(GreenhouseReading).where(
            GreenhouseReading.simulation == str(simulation),
            GreenhouseReading.plant_id == plant_id,
        )
        if not include_presence:
            query = query.where(GreenhouseReading.measurement_origin != 'signal_presence')
        return list(session.scalars(query.order_by(
            GreenhouseReading.current_state.desc(), GreenhouseReading.emitted_at.desc(),
            func.length(GreenhouseReading.event_id).desc(), GreenhouseReading.event_id.desc(),
        ).limit(server_limit)))


def latest_simulation(engine) -> str | None:
    """Retourne l'identifiant de la session la plus récente."""
    with Session(engine) as session:
        return session.scalar(
            select(SimulationRun.simulation).order_by(SimulationRun.first_received_at.desc()).limit(1)
        )


def latest_simulation_event(engine, simulation: str) -> SimulationEventRow | None:
    """Retourne le dernier événement de contrôle ou d'état de simulation."""
    with Session(engine) as session:
        return session.scalar(
            select(SimulationEventRow).where(
                SimulationEventRow.simulation == str(simulation)
            ).order_by(SimulationEventRow.received_at.desc(), SimulationEventRow.event_id.desc()).limit(1)
        )


def get_control_event(engine, control_id: str) -> SimulationEventRow | None:
    """Retrouve l'événement d'acquittement corrélé à une commande de simulation."""
    with Session(engine) as session:
        return session.scalar(
            select(SimulationEventRow).where(
                SimulationEventRow.control_id == str(control_id)
            ).limit(1)
        )
