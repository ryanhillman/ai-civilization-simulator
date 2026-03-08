from fastapi import APIRouter, HTTPException

from app.api.deps import DbSession
from app.core.config import settings
from app.domain.simulation_service import SimulationService
from app.schemas import (
    AutoplayRequest,
    RunRequest,
    TurnResultResponse,
    build_turn_result_response,
)

router = APIRouter()
_svc = SimulationService()


@router.post("/{world_id}/turns/next", response_model=TurnResultResponse)
async def next_turn(world_id: int, db: DbSession):
    try:
        result = await _svc.advance_turn(world_id, db)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return build_turn_result_response(result)


@router.post("/{world_id}/turns/run", response_model=list[TurnResultResponse])
async def run_turns(world_id: int, body: RunRequest, db: DbSession):
    try:
        results = await _svc.advance_turns(world_id, body.n, db)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return [build_turn_result_response(r) for r in results]


@router.post("/{world_id}/turns/autoplay", response_model=list[TurnResultResponse])
async def autoplay(world_id: int, body: AutoplayRequest, db: DbSession):
    n = min(body.max_turns, settings.autoplay_max_turns)
    try:
        results = await _svc.advance_turns(world_id, n, db)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return [build_turn_result_response(r) for r in results]
