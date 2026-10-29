"""Parcours explicite proposition → confirmation → suivi, sans IA."""
from greenmind.identifiers import next_id, CommandId, ProposalId

from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from greenmind.api.dependencies import get_config, get_db, get_publisher
from greenmind.api.schemas import ApiModel
from greenmind.db import arrosage as watering

router = APIRouter(prefix='/api/v1', tags=['Arrosage virtuel'])


class ProposalRequest(ApiModel):
    proposal_id: ProposalId = Field(default_factory=lambda: next_id("proposal"))


class ConfirmationRequest(ApiModel):
    proposal_id: ProposalId
    command_id: CommandId = Field(default_factory=lambda: next_id("command"))


class ProposalResponse(ApiModel):
    proposal_id: str
    simulation: str
    plant_id: str
    current_state: int
    watering_duration_s: float
    moist_before_pct: float
    moist_after_pct: float
    duration_limited: bool
    reason: str
    expires_at: str


class WateringStatusResponse(ApiModel):
    command_id: str
    proposal_id: str
    simulation: str
    plant_id: str
    status: Literal['en_attente', 'envoyé', 'exécuté', 'refusé', 'TIMED_OUT']
    reason: str
    resulting_state: int | None
    measurement_pending: bool
    expires_at: str


def require_plant(config, plant_id):
    try:
        config.get_plant(plant_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post('/plants/{plant_id}/arrosage-proposals', status_code=201, response_model=ProposalResponse)
def propose(plant_id: str, payload: ProposalRequest, db=Depends(get_db), config=Depends(get_config)):
    require_plant(config, plant_id)
    try:
        return watering.create_proposal(db, config, plant_id, payload.proposal_id)
    except watering.WateringError as error:
        watering.record_refusal(db, plant_id, str(error))
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error


@router.post('/plants/{plant_id}/arrosage-commands', status_code=202, response_model=WateringStatusResponse)
def confirm(plant_id: str, payload: ConfirmationRequest, db=Depends(get_db),
            config=Depends(get_config), publisher=Depends(get_publisher)):
    require_plant(config, plant_id)
    try:
        command, is_new = watering.confirm_proposal(db, config, plant_id, payload.proposal_id, payload.command_id)
        if is_new:
            watering.mark_sent(db, command.command_id)
            try:
                publisher.publish_watering(plant_id, command.model_dump_json())
            except Exception as error:
                watering.mark_publish_uncertain(db, command.command_id)
                raise HTTPException(status_code=503, detail={
                    'command_id': str(command.command_id),
                    'message': "Publication non confirmée ; consulter le suivi, aucun renvoi automatique.",
                }) from error
        return watering.command_status(db, command.command_id)
    except watering.WateringError as error:
        watering.record_refusal(db, plant_id, str(error))
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error


@router.get('/arrosage-commands/{command_id}', response_model=WateringStatusResponse)
def track(command_id: CommandId, db=Depends(get_db)):
    try:
        return watering.command_status(db, command_id)
    except watering.WateringError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error
