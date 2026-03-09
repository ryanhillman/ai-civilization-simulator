from fastapi import APIRouter, HTTPException

from app.ai.schemas import TurnSummaryAIRequest
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


async def _maybe_attach_ai_summary(
    responses: list[TurnResultResponse],
    world_name: str,
) -> None:
    """
    Optionally generate a narrative AI summary for multi-turn runs and
    attach it to the last response. Mutates responses[-1] in place.

    No-ops if AI is disabled, only 1 turn ran, or generation fails.
    """
    if len(responses) < 2 or not settings.ai_enabled or not settings.ai_summary_enabled:
        return

    from app.ai.service import ai_service

    turn_start = responses[0].turn_number
    turn_end = responses[-1].turn_number

    # Collect notable event descriptions across all turns (cap at 15 total)
    all_events: list[str] = []
    world_event_names: list[str] = []
    for resp in responses:
        for e in resp.events:
            if e.event_type not in ("rest",):
                all_events.append(e.description)
        for we in resp.world_events:
            world_event_names.append(we.event_type)

    request = TurnSummaryAIRequest(
        world_name=world_name,
        turn_start=turn_start,
        turn_end=turn_end,
        notable_events=all_events[:15],
        world_event_names=list(dict.fromkeys(world_event_names)),  # dedupe
    )

    ai_resp = await ai_service.generate_turn_summary(request)
    if ai_resp:
        # Attach to the last response (safe field replacement via dict trick)
        last = responses[-1]
        responses[-1] = last.model_copy(update={"ai_summary": ai_resp.narrative})


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
    responses = [build_turn_result_response(r) for r in results]
    # Resolve world name for AI summary (use first result's world_id)
    world_name = "the village"
    if results:
        from app.models.db import World
        w = await db.get(World, results[0].world_id)
        if w:
            world_name = w.name
    await _maybe_attach_ai_summary(responses, world_name)
    return responses


@router.post("/{world_id}/turns/autoplay", response_model=list[TurnResultResponse])
async def autoplay(world_id: int, body: AutoplayRequest, db: DbSession):
    n = min(body.max_turns, settings.autoplay_max_turns)
    try:
        results = await _svc.advance_turns(world_id, n, db)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    responses = [build_turn_result_response(r) for r in results]
    world_name = "the village"
    if results:
        from app.models.db import World
        w = await db.get(World, results[0].world_id)
        if w:
            world_name = w.name
    await _maybe_attach_ai_summary(responses, world_name)
    return responses
