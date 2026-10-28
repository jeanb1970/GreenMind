"""Propositions, intentions MQTT et suivi d'arrosage transactionnels."""

from datetime import datetime, timedelta, timezone
import json
from uuid import UUID, uuid4
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from greenmind.db.models import (
    GreenhouseEventRow, GreenhouseReading, SimulationRun, WateringProposalRow,
    WateringCommandRow,
)
from greenmind.domain.watering import plan_watering
from greenmind.schemas import WateringCommand, WateringEvent

FRESHNESS_SECONDS = 10
ACK_TIMEOUT_SECONDS = 10


class WateringError(ValueError):
    def __init__(self, message, status_code=409):
        super().__init__(message)
        self.status_code = status_code


def utcnow():
    return datetime.now(timezone.utc)


def utc_text(value):
    return value.astimezone(timezone.utc).isoformat(timespec='microseconds').replace('+00:00', 'Z')


def parse_date(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def journal(session, run_id, plant_id, kind, summary, details=None, simulated_at=None):
    session.add(GreenhouseEventRow(
        event_id=str(uuid4()), run_id=str(run_id), plant_id=plant_id,
        created_at=utc_text(utcnow()), simulated_at=simulated_at,
        event_type=kind, summary=summary, details_json=json.dumps(details or {}, ensure_ascii=False),
    ))


def write_lock(session):
    # Première instruction : verrou d'écriture avant toute lecture de validation.
    session.execute(update(SimulationRun).where(SimulationRun.run_id == '').values(first_received_at=''))


def latest_run(session):
    return session.scalar(select(SimulationRun.run_id).order_by(SimulationRun.first_received_at.desc()).limit(1))


def latest_sample(session, run_id, plant_id=None):
    query = select(GreenhouseReading).where(GreenhouseReading.run_id == run_id)
    if plant_id is not None:
        query = query.where(GreenhouseReading.plant_id == plant_id)
    return session.scalar(query.order_by(GreenhouseReading.state_revision.desc(),
        GreenhouseReading.emitted_at.desc(), GreenhouseReading.event_id.desc()).limit(1))


def expire_commands(session, now):
    rows = session.scalars(select(WateringCommandRow).where(
        WateringCommandRow.status.in_(['PENDING', 'SENT']),
        WateringCommandRow.expires_at <= utc_text(now),
    ))
    for row in rows:
        row.status = 'TIMED_OUT'
        row.reason = "Exécution non confirmée ; aucun renvoi automatique."
        journal(session, row.run_id, row.plant_id, 'WATERING_TIMED_OUT', row.reason,
                {'command_id': row.command_id})
    session.flush()


def ensure_watering_idle(session, run_id):
    """L'incertitude et l'attente de mesure après ACK gardent le verrou logique."""
    for row in session.scalars(select(WateringCommandRow).where(
        WateringCommandRow.run_id == run_id,
        WateringCommandRow.status.in_(['PENDING', 'SENT', 'TIMED_OUT', 'EXECUTED']),
    )):
        if row.status != 'EXECUTED':
            raise WateringError("Un arrosage est en cours ou son exécution reste incertaine.")
        sample = latest_sample(session, run_id, row.plant_id)
        if sample is None or sample.state_revision < row.resulting_revision:
            raise WateringError("Mesure après arrosage en attente ; mutation temporairement refusée.")


def validate_state(session, config, plant_id, now):
    run_id = latest_run(session)
    if run_id is None:
        raise WateringError("Aucune session de simulation active.")
    ensure_watering_idle(session, run_id)
    sample = latest_sample(session, run_id, plant_id)
    current = latest_sample(session, run_id)
    if sample is None or current is None:
        raise WateringError("Mesure du bac indisponible.", 503)
    age = (now - parse_date(sample.emitted_at)).total_seconds()
    if not 0 <= age < FRESHNESS_SECONDS or sample.state_revision != current.state_revision:
        raise WateringError("Mesure périmée ou synchronisation des bacs en attente.", 503)
    profile = config.get_plant(plant_id)
    last = session.scalar(select(WateringCommandRow).where(
        WateringCommandRow.run_id == run_id, WateringCommandRow.plant_id == plant_id,
        WateringCommandRow.status == 'EXECUTED',
    ).order_by(WateringCommandRow.executed_at.desc()).limit(1))
    if last is not None:
        remaining = profile.watering_cooldown_real_s - (now - parse_date(last.executed_at)).total_seconds()
        if remaining > 0:
            raise WateringError(f"Repos du bac : encore {remaining:.1f} secondes réelles.")
    try:
        plan = plan_watering(profile, sample.soil_moisture_sim_pct)
    except ValueError as error:
        raise WateringError(str(error)) from error
    return run_id, sample, plan


def create_proposal(engine, config, plant_id, proposal_id):
    now = utcnow()
    with Session(engine) as session, session.begin():
        write_lock(session)
        expire_commands(session, now)
        previous = session.get(WateringProposalRow, str(proposal_id))
        if previous is not None:
            if previous.plant_id != plant_id:
                raise WateringError("Clé de proposition réutilisée pour un autre bac.")
            return json.loads(previous.payload)
        run_id, sample, plan = validate_state(session, config, plant_id, now)
        expires = utc_text(now + timedelta(seconds=60))
        data = dict(proposal_id=str(proposal_id), run_id=run_id, plant_id=plant_id,
                    state_revision=sample.state_revision, duration_sim_s=plan.duration_sim_s,
                    soil_moisture_before_pct=sample.soil_moisture_sim_pct,
                    soil_moisture_after_pct=plan.soil_moisture_after_pct,
                    capped=plan.capped, reason=plan.reason, expires_at=expires)
        session.add(WateringProposalRow(
            proposal_id=str(proposal_id), run_id=run_id, plant_id=plant_id,
            state_revision=sample.state_revision, expires_at=expires, payload=json.dumps(data),
        ))
        journal(session, run_id, plant_id, 'WATERING_PROPOSED', plan.reason,
                {'proposal_id': str(proposal_id)}, sample.simulated_at)
        return data


def confirm_proposal(engine, config, plant_id, proposal_id, command_id):
    now = utcnow()
    with Session(engine) as session, session.begin():
        write_lock(session)
        expire_commands(session, now)
        previous = session.get(WateringCommandRow, str(command_id))
        if previous is not None:
            if previous.plant_id != plant_id or previous.proposal_id != str(proposal_id):
                raise WateringError("Clé de commande réutilisée avec un autre contenu.")
            return WateringCommand.model_validate_json(previous.payload), False
        proposal = session.get(WateringProposalRow, str(proposal_id))
        if proposal is None or proposal.plant_id != plant_id:
            raise WateringError("Proposition introuvable pour ce bac.", 404)
        if proposal.consumed_by is not None:
            raise WateringError("La proposition a déjà été consommée.")
        if parse_date(proposal.expires_at) <= now:
            raise WateringError("La proposition a expiré ; en demander une nouvelle.")
        run_id, sample, plan = validate_state(session, config, plant_id, now)
        if run_id != proposal.run_id or sample.state_revision != proposal.state_revision:
            raise WateringError("L'état a changé depuis la proposition ; en demander une nouvelle.")
        command = WateringCommand(
            command_id=UUID(str(command_id)), run_id=UUID(run_id), plant_id=plant_id,
            actuator_id=config.get_plant(plant_id).actuator_id,
            duration_sim_s=plan.duration_sim_s, expected_revision=sample.state_revision,
            requested_at=now, expires_at=now + timedelta(seconds=ACK_TIMEOUT_SECONDS),
        )
        session.add(WateringCommandRow(
            command_id=str(command_id), proposal_id=str(proposal_id), run_id=run_id,
            plant_id=plant_id, status='PENDING', expires_at=utc_text(command.expires_at),
            payload=command.model_dump_json(), reason="Confirmation enregistrée avant publication MQTT.",
        ))
        proposal.consumed_by = str(command_id)
        journal(session, run_id, plant_id, 'WATERING_PENDING', 'Arrosage confirmé, publication en attente.',
                {'command_id': str(command_id)}, sample.simulated_at)
        return command, True


def mark_sent(engine, command_id):
    with Session(engine) as session, session.begin():
        write_lock(session)
        row = session.get(WateringCommandRow, str(command_id))
        if row.status == 'PENDING':
            row.status = 'SENT'
            row.reason = "Envoi MQTT engagé ; acquittement métier en attente."
            journal(session, row.run_id, row.plant_id, 'WATERING_SENT', row.reason,
                    {'command_id': str(command_id)})


def mark_publish_uncertain(engine, command_id):
    with Session(engine) as session, session.begin():
        write_lock(session)
        row = session.get(WateringCommandRow, str(command_id))
        if row.status in ('PENDING', 'SENT'):
            row.status = 'TIMED_OUT'
            row.reason = "Publication non confirmée ; exécution incertaine, aucun renvoi automatique."
            journal(session, row.run_id, row.plant_id, 'WATERING_PUBLISH_FAILED', row.reason,
                    {'command_id': str(command_id)})


def record_watering_event(session, message: WateringEvent):
    row = session.get(WateringCommandRow, str(message.command_id))
    if row is None or row.run_id != str(message.run_id) or row.plant_id != message.plant_id:
        journal(session, message.run_id, message.plant_id, 'WATERING_UNMATCHED',
                "Acquittement sans commande correspondante.", {'command_id': str(message.command_id)})
        return
    if row.status in ('EXECUTED', 'REJECTED'):
        return
    command = WateringCommand.model_validate_json(row.payload)
    if message.status == 'APPLIED' and (
        message.resulting_revision != command.expected_revision + 1
        or abs(message.duration_applied_sim_s - command.duration_sim_s) > 1e-9
    ):
        raise ValueError("Acquittement incohérent avec la commande d'arrosage.")
    late = row.status == 'TIMED_OUT' or parse_date(row.expires_at) <= utcnow()
    row.status = 'EXECUTED' if message.status == 'APPLIED' else 'REJECTED'
    row.reason = message.reason
    row.resulting_revision = message.resulting_revision
    if message.status == 'APPLIED':
        row.executed_at = utc_text(message.emitted_at)
    journal(session, row.run_id, row.plant_id, f'WATERING_{row.status}', message.reason,
            {'command_id': row.command_id, 'late_ack': late}, utc_text(message.simulated_at))


def command_status(engine, command_id):
    with Session(engine) as session, session.begin():
        write_lock(session)
        expire_commands(session, utcnow())
        row = session.get(WateringCommandRow, str(command_id))
        if row is None:
            raise WateringError("Commande d'arrosage inconnue.", 404)
        sample = latest_sample(session, row.run_id, row.plant_id)
        pending_measurement = row.status == 'EXECUTED' and (
            sample is None or sample.state_revision < row.resulting_revision)
        return dict(command_id=row.command_id, proposal_id=row.proposal_id, run_id=row.run_id,
                    plant_id=row.plant_id, status=row.status, reason=row.reason,
                    resulting_revision=row.resulting_revision,
                    measurement_pending=pending_measurement, expires_at=row.expires_at)


def record_refusal(engine, plant_id, reason):
    with Session(engine) as session, session.begin():
        write_lock(session)
        expire_commands(session, utcnow())
        run_id = latest_run(session)
        if run_id is not None:
            journal(session, run_id, plant_id, 'WATERING_REFUSED', reason)
