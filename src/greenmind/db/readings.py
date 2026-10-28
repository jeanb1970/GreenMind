"""Persistance atomique et lecture des mesures, alertes et journal de la serre."""

from datetime import datetime, timezone
from functools import lru_cache
import json
from pathlib import Path
from uuid import UUID, uuid4
from sqlalchemy import select
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
from greenmind.schemas import SimulationControl, SimulationEvent, TelemetryV2, WateringEvent

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config/greenhouse.yaml"


@lru_cache(maxsize=1)
def get_default_greenhouse_config() -> GreenhouseConfig:
    return load_greenhouse_config(DEFAULT_CONFIG_PATH)


def _utc_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _handle_telemetry_side_effects(
    session: Session,
    message: TelemetryV2,
    received_at: str,
    config: GreenhouseConfig,
) -> None:
    """Ouvre ou ferme atomiquement l'alerte de sécheresse et alimente le journal."""
    bed = config.get_plant(message.plant_id)
    active = session.scalar(
        select(AlertRow).where(
            AlertRow.run_id == str(message.run_id),
            AlertRow.plant_id == message.plant_id,
            AlertRow.status == "OPEN",
        ).order_by(AlertRow.opened_at.desc()).limit(1)
    )
    is_currently_open = active is not None
    should_be_open = next_dry_alert_state(
        message.soil_moisture_sim_pct,
        alert_open=is_currently_open,
        low_threshold_sim_pct=bed.low_threshold_sim_pct,
        rearm_threshold_sim_pct=bed.rearm_threshold_sim_pct,
    )

    if not is_currently_open and should_be_open:
        new_alert_id = str(uuid4())
        session.add(AlertRow(
            alert_id=new_alert_id,
            run_id=str(message.run_id),
            plant_id=message.plant_id,
            status="OPEN",
            opened_at=received_at,
            opening_event_id=str(message.event_id),
            trigger_moisture_pct=message.soil_moisture_sim_pct,
        ))
        session.add(GreenhouseEventRow(
            event_id=str(uuid4()),
            run_id=str(message.run_id),
            plant_id=message.plant_id,
            created_at=received_at,
            simulated_at=_utc_text(message.simulated_at),
            event_type="ALERT_OPENED",
            summary=f"Alerte de sécheresse ouverte sur {bed.display_name} ({message.soil_moisture_sim_pct:.1f} % < {bed.low_threshold_sim_pct:.1f} %).",
            details_json=json.dumps({
                "alert_id": new_alert_id,
                "plant_id": message.plant_id,
                "trigger_moisture_pct": message.soil_moisture_sim_pct,
                "low_threshold_sim_pct": bed.low_threshold_sim_pct,
            }),
        ))
    elif is_currently_open and not should_be_open and active is not None:
        active.status = "CLOSED"
        active.closed_at = received_at
        active.closing_event_id = str(message.event_id)
        active.resolved_moisture_pct = message.soil_moisture_sim_pct
        session.add(GreenhouseEventRow(
            event_id=str(uuid4()),
            run_id=str(message.run_id),
            plant_id=message.plant_id,
            created_at=received_at,
            simulated_at=_utc_text(message.simulated_at),
            event_type="ALERT_CLOSED",
            summary=f"Alerte de sécheresse levée sur {bed.display_name} ({message.soil_moisture_sim_pct:.1f} % >= {bed.rearm_threshold_sim_pct:.1f} %).",
            details_json=json.dumps({
                "alert_id": active.alert_id,
                "plant_id": message.plant_id,
                "resolved_moisture_pct": message.soil_moisture_sim_pct,
                "rearm_threshold_sim_pct": bed.rearm_threshold_sim_pct,
            }),
        ))

    if message.measurement_origin == "manual_override":
        session.add(GreenhouseEventRow(
            event_id=str(uuid4()),
            run_id=str(message.run_id),
            plant_id=message.plant_id,
            created_at=received_at,
            simulated_at=_utc_text(message.simulated_at),
            event_type="MANUAL_OVERRIDE",
            summary=f"Humidité imposée à {message.soil_moisture_sim_pct:.1f} % sur {bed.display_name}.",
            details_json=json.dumps({
                "plant_id": message.plant_id,
                "soil_moisture_sim_pct": message.soil_moisture_sim_pct,
            }),
        ))


def _handle_simulation_event_side_effects(
    session: Session,
    message: SimulationEvent,
    received_at: str,
) -> None:
    if message.control_id is not None:
        session.add(GreenhouseEventRow(
            event_id=str(uuid4()),
            run_id=str(message.run_id),
            plant_id=None,
            created_at=received_at,
            simulated_at=_utc_text(message.simulated_at),
            event_type=f"CONTROL_{message.status}",
            summary=message.reason,
            details_json=json.dumps({
                "control_id": str(message.control_id),
                "status": message.status,
                "state_revision": message.state_revision,
                "reason": message.reason,
            }),
        ))


def save_message(
    engine,
    message: TelemetryV2 | SimulationEvent | WateringEvent,
    *,
    config: GreenhouseConfig | None = None,
) -> bool:
    """Enregistre le message et applique les effets d'alerte et de journal de manière atomique."""
    received_at = _utc_text(datetime.now(timezone.utc))
    if isinstance(message, TelemetryV2):
        model = GreenhouseReading
        values = message.model_dump()
        for key in ("event_id", "run_id"):
            values[key] = str(values[key])
        for key in ("observed_at", "simulated_at", "emitted_at"):
            values[key] = _utc_text(values[key])
        values["received_at"] = received_at
    elif isinstance(message, WateringEvent):
        model = WateringEventRow
        values = dict(event_id=str(message.event_id), run_id=str(message.run_id),
                      command_id=str(message.command_id), received_at=received_at,
                      payload=message.model_dump_json())
    else:
        model = SimulationEventRow
        values = dict(event_id=str(message.event_id), run_id=str(message.run_id),
                      control_id=str(message.control_id) if message.control_id else None,
                      received_at=received_at, payload=message.model_dump_json())

    active_config = config or get_default_greenhouse_config()

    with Session(engine) as session, session.begin():
        session.execute(insert(SimulationRun).values(
            run_id=str(message.run_id), first_received_at=received_at,
        ).on_conflict_do_nothing(index_elements=["run_id"]))

        inserted = session.scalar(insert(model).values(**values)
                                  .on_conflict_do_nothing(index_elements=["event_id"])
                                  .returning(model.event_id))

        if inserted is not None:
            if isinstance(message, TelemetryV2):
                # Conserver les mesures tardives dans l'historique sans rejouer
                # les transitions d'alerte ni les forçages d'un état dépassé.
                current_id = session.scalar(select(GreenhouseReading.event_id).where(
                    GreenhouseReading.run_id == str(message.run_id),
                    GreenhouseReading.plant_id == message.plant_id,
                ).order_by(GreenhouseReading.state_revision.desc(),
                           GreenhouseReading.emitted_at.desc(),
                           GreenhouseReading.event_id.desc()).limit(1))
                if current_id == str(message.event_id):
                    _handle_telemetry_side_effects(session, message, received_at, active_config)
            elif isinstance(message, WateringEvent):
                from greenmind.db.watering import record_watering_event
                record_watering_event(session, message)
            else:
                _handle_simulation_event_side_effects(session, message, received_at)

    return inserted is not None


def latest_reading(engine, run_id: str | UUID, plant_id: str) -> GreenhouseReading | None:
    """Une mesure tardive d'une ancienne révision ne remplace jamais l'état actuel."""
    with Session(engine) as session:
        return session.scalar(select(GreenhouseReading).where(
            GreenhouseReading.run_id == str(run_id), GreenhouseReading.plant_id == plant_id,
        ).order_by(GreenhouseReading.state_revision.desc(),
                   GreenhouseReading.emitted_at.desc(), GreenhouseReading.event_id.desc()).limit(1))


def reserve_control(engine, command: SimulationControl) -> SimulationControl:
    """Réserve une clé atomiquement ; un rejeu conserve le message original.

    L'INSERT prend le verrou d'écriture SQLite avant la vérification de révision.
    Les requêtes concurrentes et les redémarrages utilisent ainsi le même contrat.
    """
    with Session(engine) as session, session.begin():
        inserted = session.scalar(insert(SimulationControlRow).values(
            control_id=str(command.control_id), run_id=str(command.run_id),
            payload=command.model_dump_json(),
        ).on_conflict_do_nothing(index_elements=["control_id"])
          .returning(SimulationControlRow.control_id))
        if inserted is None:
            row = session.get(SimulationControlRow, str(command.control_id))
            original = SimulationControl.model_validate_json(row.payload)
            fields = ("action", "expected_revision", "plant_id", "value")
            if any(getattr(original, key) != getattr(command, key) for key in fields):
                raise ValueError("Identifiant de contrôle réutilisé avec un contenu différent.")
            return original

        from greenmind.db.watering import ensure_watering_idle
        ensure_watering_idle(session, str(command.run_id))

        sample = session.scalar(select(GreenhouseReading).where(
            GreenhouseReading.run_id == str(command.run_id),
        ).order_by(GreenhouseReading.state_revision.desc(),
                   GreenhouseReading.emitted_at.desc()).limit(1))
        if sample is None or sample.state_revision != command.expected_revision:
            raise ValueError("Conflit de révision d'état : la révision attendue n'est plus courante.")
        return command


def active_alert(engine, run_id: str | UUID, plant_id: str) -> AlertRow | None:
    """Retourne l'alerte ouverte pour un bac dans la session courante."""
    with Session(engine) as session:
        return session.scalar(select(AlertRow).where(
            AlertRow.run_id == str(run_id),
            AlertRow.plant_id == plant_id,
            AlertRow.status == "OPEN",
        ).order_by(AlertRow.opened_at.desc()).limit(1))


def list_alerts(engine, run_id: str | UUID, plant_id: str | None = None) -> list[AlertRow]:
    """Retourne l'historique des alertes pour la session, optionnellement filtré par bac."""
    with Session(engine) as session:
        query = select(AlertRow).where(AlertRow.run_id == str(run_id))
        if plant_id is not None:
            query = query.where(AlertRow.plant_id == plant_id)
        return list(session.scalars(query.order_by(AlertRow.opened_at.desc())))


def list_events(
    engine,
    run_id: str | UUID,
    plant_id: str | None = None,
    limit: int = 100,
) -> list[GreenhouseEventRow]:
    """100 derniers événements de la session courante, avec filtre bac optionnel."""
    server_limit = min(max(1, limit), 100)
    with Session(engine) as session:
        query = select(GreenhouseEventRow).where(GreenhouseEventRow.run_id == str(run_id))
        if plant_id is not None:
            query = query.where(GreenhouseEventRow.plant_id == plant_id)
        return list(session.scalars(query.order_by(GreenhouseEventRow.sequence.desc()).limit(server_limit)))


def recent_readings(
    engine,
    run_id: str | UUID,
    plant_id: str,
    limit: int = 24,
) -> list[GreenhouseReading]:
    """Mesures récentes d'un bac pour l'exécution courante, limite serveur imposée."""
    server_limit = min(max(1, limit), 100)
    with Session(engine) as session:
        return list(session.scalars(
            select(GreenhouseReading).where(
                GreenhouseReading.run_id == str(run_id),
                GreenhouseReading.plant_id == plant_id,
            ).order_by(GreenhouseReading.state_revision.desc(),
                       GreenhouseReading.emitted_at.desc()).limit(server_limit)
        ))


def latest_run_id(engine) -> str | None:
    """Retourne l'identifiant de la session la plus récente."""
    with Session(engine) as session:
        return session.scalar(
            select(SimulationRun.run_id).order_by(SimulationRun.first_received_at.desc()).limit(1)
        )


def latest_simulation_event(engine, run_id: str | UUID) -> SimulationEventRow | None:
    """Retourne le dernier événement de contrôle ou d'état de simulation."""
    with Session(engine) as session:
        return session.scalar(
            select(SimulationEventRow).where(
                SimulationEventRow.run_id == str(run_id)
            ).order_by(SimulationEventRow.received_at.desc(), SimulationEventRow.event_id.desc()).limit(1)
        )


def get_control_event(engine, control_id: str | UUID) -> SimulationEventRow | None:
    """Retrouve l'événement d'acquittement corrélé à une commande de simulation."""
    with Session(engine) as session:
        return session.scalar(
            select(SimulationEventRow).where(
                SimulationEventRow.control_id == str(control_id)
            ).limit(1)
        )
