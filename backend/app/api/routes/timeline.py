from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from app.api.deps import DbSession
from app.models.db import TurnEvent, World
from app.schemas import TurnEventResponse

router = APIRouter()


@router.get("/{world_id}/timeline", response_model=list[TurnEventResponse])
async def get_timeline(
    world_id: int,
    db: DbSession,
    turn: Optional[int] = Query(default=None),
    agent_id: Optional[int] = Query(default=None),
    event_type: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
):
    world = await db.get(World, world_id)
    if world is None:
        raise HTTPException(status_code=404, detail=f"World {world_id} not found")

    stmt = (
        select(TurnEvent)
        .where(TurnEvent.world_id == world_id)
        .order_by(TurnEvent.turn_number.desc(), TurnEvent.id.asc())
        .limit(limit)
    )

    if turn is not None:
        stmt = stmt.where(TurnEvent.turn_number == turn)

    if event_type is not None:
        stmt = stmt.where(TurnEvent.event_type == event_type)

    result = await db.execute(stmt)
    events = result.scalars().all()

    # Filter by agent_id in Python (agent_ids is JSONB array)
    if agent_id is not None:
        events = [e for e in events if agent_id in (e.agent_ids or [])]

    return events
