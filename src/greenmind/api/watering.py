"""Parcours explicite proposition → confirmation → suivi, sans IA."""

from uuid import UUID, uuid4
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from greenmind.api.dependencies import get_config, get_db, get_publisher
from greenmind.api.schemas import ApiModel
from greenmind.db import watering

router = APIRouter(prefix='/api/v1', tags=['Arrosage virtuel'])


class ProposalRequest(ApiModel):
    proposal_id: UUID = Field(default_factory=uuid4)


class ConfirmationRequest(ApiModel):
    proposal_id: UUID
    command_id: UUID = Field(default_factory=uuid4)


class ProposalResponse(ApiModel):
    proposal_id: str
    run_id: str
    plant_id: str
    state_revision: int
    duration_sim_s: float
    soil_moisture_before_pct: float
    soil_moisture_after_pct: float
    capped: bool
    reason: str
    expires_at: str


class WateringStatusResponse(ApiModel):
    command_id: str
    proposal_id: str
    run_id: str
    plant_id: str
    status: Literal['PENDING', 'SENT', 'EXECUTED', 'REJECTED', 'TIMED_OUT']
    reason: str
    resulting_revision: int | None
    measurement_pending: bool
    expires_at: str


def require_plant(config, plant_id):
    try:
        config.get_plant(plant_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post('/plants/{plant_id}/watering-proposals', status_code=201, response_model=ProposalResponse)
def propose(plant_id: str, payload: ProposalRequest, db=Depends(get_db), config=Depends(get_config)):
    require_plant(config, plant_id)
    try:
        return watering.create_proposal(db, config, plant_id, payload.proposal_id)
    except watering.WateringError as error:
        watering.record_refusal(db, plant_id, str(error))
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error


@router.post('/plants/{plant_id}/watering-commands', status_code=202, response_model=WateringStatusResponse)
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


@router.get('/watering-commands/{command_id}', response_model=WateringStatusResponse)
def track(command_id: UUID, db=Depends(get_db)):
    try:
        return watering.command_status(db, command_id)
    except watering.WateringError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error
