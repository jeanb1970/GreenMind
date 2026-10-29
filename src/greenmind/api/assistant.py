"""Question sur un bac : faits SQLite et explication documentaire sans action."""
from greenmind.simulation_rules import PRESENCE_TTL_SECONDS
from datetime import datetime, timezone
from typing import Literal, Any
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field
from sqlalchemy import select, func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from greenmind.api.dependencies import get_config, get_db
from greenmind.api.schemas import ApiModel
from greenmind.db.models import GreenhouseReading, SimulationRun, AlertRow
from greenmind.time_formats import parse_local

router = APIRouter(prefix='/api/v1', tags=['Assistant horticole local'])


class AskRequest(ApiModel):
    plant_id: str = Field(min_length=1, max_length=50)
    question: str = Field(min_length=1, max_length=1000)


class AssistantResponse(ApiModel):
    plant_id: str
    status: Literal['répondu', 'sources_insuffisantes', 'indisponible', 'occupé', 'action_non_exécutée']
    facts: dict[str, Any]
    explanation: str
    sources: list[dict[str, Any]]
    action_executed: Literal[False] = False


def get_assistant(request: Request):
    service = getattr(request.app.state, 'assistant', None)
    if service is None:
        raise HTTPException(status_code=503, detail='Assistant non initialisé.')
    return service


@router.get('/assistant/health')
async def assistant_health(request: Request):
    service = getattr(request.app.state, 'assistant', None)
    if service is None:
        return dict(available=False, status='indisponible', reason='Assistant non initialisé.')
    return await service.availability()


def collect_facts(db, config, plant):
    profile = config.get_plant(plant)
    # Cette transaction est fermée avant la recherche et toute génération LLM.
    with Session(db) as session, session.begin():
        simulation = session.scalar(select(SimulationRun.simulation).order_by(SimulationRun.first_received_at.desc()).limit(1))
        sample = session.scalar(select(GreenhouseReading).where(
            GreenhouseReading.simulation == simulation, GreenhouseReading.plant_id == plant,
        ).order_by(GreenhouseReading.current_state.desc(), GreenhouseReading.emitted_at.desc(),
                   func.length(GreenhouseReading.event_id).desc(), GreenhouseReading.event_id.desc()).limit(1))
        alert = session.scalar(select(AlertRow.alert_id).where(
            AlertRow.simulation == simulation, AlertRow.plant_id == plant, AlertRow.status == 'ouverte').limit(1))
        facts = dict(simulation=simulation, plant_id=plant, display_name=profile.display_name,
                     moist_low_pct=profile.moist_low_pct, moist_rearm_pct=profile.moist_rearm_pct,
                     moist_target_pct=profile.moist_target_pct, has_active_alert=alert is not None)
        if sample is None:
            return {**facts, 'measurement_available': False, 'fresh': False}
        facts.update({key: getattr(sample, key) for key in (
            'soil_moisture_pct', 'air_temperature_c', 'air_humidity_pct', 'measurement_origin',
            'provenance', 'emitted_at', 'simulated_at', 'current_state', 'cycle', 'heure_virtuelle', 'paused', 'day_complete')})
        age = (datetime.now(timezone.utc) - parse_local(sample.emitted_at)).total_seconds()
        return {**facts, 'measurement_available': True, 'fresh': 0 <= age < PRESENCE_TTL_SECONDS}


@router.post('/assistant/ask', response_model=AssistantResponse)
async def ask(payload: AskRequest, db=Depends(get_db), config=Depends(get_config), assistant=Depends(get_assistant)):
    if not payload.question.strip():
        raise HTTPException(status_code=422, detail='La question ne peut pas être vide.')
    try:
        config.get_plant(payload.plant_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail='Plante inconnue.') from error
    try:
        facts = await run_in_threadpool(collect_facts, db, config, payload.plant_id)
    except SQLAlchemyError as error:
        raise HTTPException(status_code=503, detail='Les données du bac sont indisponibles.') from error
    if not facts['measurement_available']:
        result = dict(status='sources_insuffisantes', explanation='Aucune mesure disponible pour cette simulation.', sources=[])
    else:
        result = await assistant.explain(payload.question.strip(), payload.plant_id, facts)
    if facts['measurement_available']:
        age = (datetime.now(timezone.utc) - parse_local(facts['emitted_at'])).total_seconds()
        facts['fresh'] = 0 <= age < PRESENCE_TTL_SECONDS
    return AssistantResponse(plant_id=payload.plant_id, facts=facts, **result)
