"""Propositions, intentions MQTT et suivi d'arrosage transactionnels."""
from greenmind.time_formats import local_text, parse_local
from greenmind.identifiers import next_id

from datetime import datetime, timedelta, timezone
import json
from sqlalchemy import func, select, update
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


def instant_text(value):
    return local_text(value)


def parse_date(value):
    return parse_local(value)


def journal(session, simulation, plant_id, kind, summary, details=None, simulated_at=None):
    session.add(GreenhouseEventRow(
        event_id=next_id("event"), simulation=str(simulation), plant_id=plant_id,
        created_at=instant_text(utcnow()), simulated_at=simulated_at,
        event_type=kind, summary=summary, details=json.dumps(details or {}, ensure_ascii=False),
    ))


def write_lock(session):
    # Première instruction : verrou d'écriture avant toute lecture de validation.
    session.execute(update(SimulationRun).where(SimulationRun.simulation == '').values(first_received_at=''))


def latest_run(session):
    return session.scalar(select(SimulationRun.simulation).order_by(SimulationRun.first_received_at.desc()).limit(1))


def latest_sample(session, simulation, plant_id=None):
    query = select(GreenhouseReading).where(GreenhouseReading.simulation == simulation)
    if plant_id is not None:
        query = query.where(GreenhouseReading.plant_id == plant_id)
    return session.scalar(query.order_by(GreenhouseReading.current_state.desc(),
        GreenhouseReading.emitted_at.desc(), func.length(GreenhouseReading.event_id).desc(), GreenhouseReading.event_id.desc()).limit(1))


def expire_commands(session, now):
    rows = session.scalars(select(WateringCommandRow).where(
        WateringCommandRow.status.in_(['en_attente', 'envoyé']),
        WateringCommandRow.expires_at <= instant_text(now),
    ))
    for row in rows:
        row.status = 'TIMED_OUT'
        row.reason = "Exécution non confirmée ; aucun renvoi automatique."
        journal(session, row.simulation, row.plant_id, 'arrosage_TIMED_OUT', row.reason,
                {'command_id': row.command_id})
    session.flush()


def ensure_watering_idle(session, simulation):
    """L'incertitude et l'attente de mesure après ACK gardent le verrou logique."""
    for row in session.scalars(select(WateringCommandRow).where(
        WateringCommandRow.simulation == simulation,
        WateringCommandRow.status.in_(['en_attente', 'envoyé', 'TIMED_OUT', 'exécuté']),
    )):
        if row.status != 'exécuté':
            raise WateringError("Un arrosage est en cours ou son exécution reste incertaine.")
        sample = latest_sample(session, simulation, row.plant_id)
        if sample is None or sample.current_state < row.resulting_state:
            raise WateringError("Mesure après arrosage en attente ; mutation temporairement refusée.")


def validate_state(session, config, plant_id, now):
    simulation = latest_run(session)
    if simulation is None:
        raise WateringError("Aucune session de simulation active.")
    ensure_watering_idle(session, simulation)
    sample = latest_sample(session, simulation, plant_id)
    current = latest_sample(session, simulation)
    if sample is None or current is None:
        raise WateringError("Mesure du bac indisponible.", 503)
    age = (now - parse_date(sample.emitted_at)).total_seconds()
    if not 0 <= age < FRESHNESS_SECONDS or sample.current_state != current.current_state:
        raise WateringError("Mesure périmée ou synchronisation des bacs en attente.", 503)
    profile = config.get_plant(plant_id)
    last = session.scalar(select(WateringCommandRow).where(
        WateringCommandRow.simulation == simulation, WateringCommandRow.plant_id == plant_id,
        WateringCommandRow.status == 'exécuté',
    ).order_by(WateringCommandRow.executed_at.desc()).limit(1))
    if last is not None:
        remaining = profile.watering_rest_s - (now - parse_date(last.executed_at)).total_seconds()
        if remaining > 0:
            raise WateringError(f"Repos du bac : encore {remaining:.1f} secondes réelles.")
    try:
        plan = plan_watering(profile, sample.soil_moisture_pct)
    except ValueError as error:
        raise WateringError(str(error)) from error
    return simulation, sample, plan


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
        simulation, sample, plan = validate_state(session, config, plant_id, now)
        expires = instant_text(now + timedelta(seconds=60))
        data = dict(proposal_id=str(proposal_id), simulation=simulation, plant_id=plant_id,
                    current_state=sample.current_state, watering_duration_s=plan.watering_duration_s,
                    moist_before_pct=sample.soil_moisture_pct,
                    moist_after_pct=plan.moist_after_pct,
                    duration_limited=plan.duration_limited, reason=plan.reason, expires_at=expires)
        session.add(WateringProposalRow(
            proposal_id=str(proposal_id), simulation=simulation, plant_id=plant_id,
            current_state=sample.current_state, expires_at=expires, payload=json.dumps(data),
        ))
        journal(session, simulation, plant_id, 'arrosage_proposé', plan.reason,
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
        if proposal.consumed_by_command is not None:
            raise WateringError("La proposition a déjà été consommée.")
        if parse_date(proposal.expires_at) <= now:
            raise WateringError("La proposition a expiré ; en demander une nouvelle.")
        simulation, sample, plan = validate_state(session, config, plant_id, now)
        if simulation != proposal.simulation or sample.current_state != proposal.current_state:
            raise WateringError("L'état a changé depuis la proposition ; en demander une nouvelle.")
        command = WateringCommand(
            command_id=str(command_id), simulation=simulation, plant_id=plant_id,
            arroseur_id=config.get_plant(plant_id).arroseur_id,
            watering_duration_s=plan.watering_duration_s, expected_state=sample.current_state,
            requested_at=now, expires_at=now + timedelta(seconds=ACK_TIMEOUT_SECONDS),
        )
        session.add(WateringCommandRow(
            command_id=str(command_id), proposal_id=str(proposal_id), simulation=simulation,
            plant_id=plant_id, status='en_attente', expires_at=instant_text(command.expires_at),
            payload=command.model_dump_json(), reason="Confirmation enregistrée avant publication MQTT.",
        ))
        proposal.consumed_by_command = str(command_id)
        journal(session, simulation, plant_id, 'arrosage_en_attente', 'Arrosage confirmé, publication en attente.',
                {'command_id': str(command_id)}, sample.simulated_at)
        return command, True


def mark_sent(engine, command_id):
    with Session(engine) as session, session.begin():
        write_lock(session)
        row = session.get(WateringCommandRow, str(command_id))
        if row.status == 'en_attente':
            row.status = 'envoyé'
            row.reason = "Envoi MQTT engagé ; acquittement métier en attente."
            journal(session, row.simulation, row.plant_id, 'arrosage_envoyé', row.reason,
                    {'command_id': str(command_id)})


def mark_publish_uncertain(engine, command_id):
    with Session(engine) as session, session.begin():
        write_lock(session)
        row = session.get(WateringCommandRow, str(command_id))
        if row.status in ('en_attente', 'envoyé'):
            row.status = 'TIMED_OUT'
            row.reason = "Publication non confirmée ; exécution incertaine, aucun renvoi automatique."
            journal(session, row.simulation, row.plant_id, 'arrosage_envoi_non_confirmé', row.reason,
                    {'command_id': str(command_id)})


def record_watering_event(session, message: WateringEvent):
    row = session.get(WateringCommandRow, str(message.command_id))
    if row is None or row.simulation != str(message.simulation) or row.plant_id != message.plant_id:
        journal(session, message.simulation, message.plant_id, 'arrosage_sans_précommande',
                "Acquittement sans commande correspondante.", {'command_id': str(message.command_id)})
        return
    if row.status in ('exécuté', 'refusé'):
        return
    command = WateringCommand.model_validate_json(row.payload)
    if message.status == 'appliqué' and (
        message.resulting_state != command.expected_state + 1
        or abs(message.watering_applied_duration_s - command.watering_duration_s) > 1e-9
    ):
        raise ValueError("Acquittement incohérent avec la commande d'arrosage.")
    late = row.status == 'TIMED_OUT' or parse_date(row.expires_at) <= utcnow()
    row.status = 'exécuté' if message.status == 'appliqué' else 'refusé'
    row.reason = message.reason
    row.resulting_state = message.resulting_state
    if message.status == 'appliqué':
        row.executed_at = instant_text(message.emitted_at)
    journal(session, row.simulation, row.plant_id, f'arrosage_{row.status}', message.reason,
            {'command_id': row.command_id, 'late_ack': late}, local_text(message.simulated_at, False))


def command_status(engine, command_id):
    with Session(engine) as session, session.begin():
        write_lock(session)
        expire_commands(session, utcnow())
        row = session.get(WateringCommandRow, str(command_id))
        if row is None:
            raise WateringError("Commande d'arrosage inconnue.", 404)
        sample = latest_sample(session, row.simulation, row.plant_id)
        pending_measurement = row.status == 'exécuté' and (
            sample is None or sample.current_state < row.resulting_state)
        return dict(command_id=row.command_id, proposal_id=row.proposal_id, simulation=row.simulation,
                    plant_id=row.plant_id, status=row.status, reason=row.reason,
                    resulting_state=row.resulting_state,
                    measurement_pending=pending_measurement, expires_at=row.expires_at)


def record_refusal(engine, plant_id, reason):
    with Session(engine) as session, session.begin():
        write_lock(session)
        expire_commands(session, utcnow())
        simulation = latest_run(session)
        if simulation is not None:
            journal(session, simulation, plant_id, 'demande_arrosage_refusée', reason)
