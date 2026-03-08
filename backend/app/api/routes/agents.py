from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import DbSession
from app.models.db import Agent, World
from app.schemas import (
    AgentDetailResponse,
    AgentSummaryResponse,
    InventoryResponse,
    MemoryResponse,
    RelationshipResponse,
    build_inventory_response,
)

router = APIRouter()


async def _get_agent_or_404(world_id: int, agent_id: int, db: DbSession) -> Agent:
    stmt = (
        select(Agent)
        .where(Agent.id == agent_id, Agent.world_id == world_id)
        .options(
            selectinload(Agent.inventory),
            selectinload(Agent.memories),
            selectinload(Agent.outgoing_relationships),
        )
    )
    result = await db.execute(stmt)
    agent = result.scalar_one_or_none()
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found in world {world_id}")
    return agent


@router.get("/{world_id}/agents", response_model=list[AgentSummaryResponse])
async def list_agents(world_id: int, db: DbSession):
    # Confirm world exists
    world = await db.get(World, world_id)
    if world is None:
        raise HTTPException(status_code=404, detail=f"World {world_id} not found")

    stmt = select(Agent).where(Agent.world_id == world_id).order_by(Agent.id)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/{world_id}/agents/{agent_id}", response_model=AgentDetailResponse)
async def get_agent(world_id: int, agent_id: int, db: DbSession):
    agent = await _get_agent_or_404(world_id, agent_id, db)

    # Build name map for relationship enrichment
    all_agents_result = await db.execute(
        select(Agent.id, Agent.name).where(Agent.world_id == world_id)
    )
    name_map: dict[int, str] = {row.id: row.name for row in all_agents_result}

    relationships = [
        RelationshipResponse(
            id=r.id,
            source_agent_id=r.source_agent_id,
            target_agent_id=r.target_agent_id,
            target_name=name_map.get(r.target_agent_id),
            trust=r.trust,
            warmth=r.warmth,
            respect=r.respect,
            resentment=r.resentment,
            fear=r.fear,
            alliance_active=r.alliance_active,
            grudge_active=r.grudge_active,
        )
        for r in agent.outgoing_relationships
    ]

    memories = [
        MemoryResponse(
            id=m.id,
            agent_id=m.agent_id,
            world_id=m.world_id,
            turn_number=m.turn_number,
            event_type=m.event_type,
            summary=m.summary,
            emotional_weight=m.emotional_weight,
            related_agent_id=m.related_agent_id,
            related_agent_name=name_map.get(m.related_agent_id) if m.related_agent_id else None,
            visibility=m.visibility.value,
            created_at=m.created_at,
        )
        for m in sorted(agent.memories, key=lambda m: m.turn_number, reverse=True)
    ]

    return AgentDetailResponse(
        id=agent.id,
        name=agent.name,
        profession=agent.profession,
        age=agent.age,
        is_alive=agent.is_alive,
        is_sick=agent.is_sick,
        hunger=agent.hunger,
        personality_traits=agent.personality_traits or {},
        goals=agent.goals or [],
        inventory=build_inventory_response(agent.inventory),
        relationships=relationships,
        recent_memories=memories[:20],
    )


@router.get("/{world_id}/agents/{agent_id}/memories", response_model=list[MemoryResponse])
async def get_agent_memories(world_id: int, agent_id: int, db: DbSession):
    agent = await _get_agent_or_404(world_id, agent_id, db)

    all_agents_result = await db.execute(
        select(Agent.id, Agent.name).where(Agent.world_id == world_id)
    )
    name_map: dict[int, str] = {row.id: row.name for row in all_agents_result}

    return [
        MemoryResponse(
            id=m.id,
            agent_id=m.agent_id,
            world_id=m.world_id,
            turn_number=m.turn_number,
            event_type=m.event_type,
            summary=m.summary,
            emotional_weight=m.emotional_weight,
            related_agent_id=m.related_agent_id,
            related_agent_name=name_map.get(m.related_agent_id) if m.related_agent_id else None,
            visibility=m.visibility.value,
            created_at=m.created_at,
        )
        for m in sorted(agent.memories, key=lambda m: m.turn_number, reverse=True)
    ]


@router.get("/{world_id}/agents/{agent_id}/relationships", response_model=list[RelationshipResponse])
async def get_agent_relationships(world_id: int, agent_id: int, db: DbSession):
    agent = await _get_agent_or_404(world_id, agent_id, db)

    all_agents_result = await db.execute(
        select(Agent.id, Agent.name).where(Agent.world_id == world_id)
    )
    name_map: dict[int, str] = {row.id: row.name for row in all_agents_result}

    return [
        RelationshipResponse(
            id=r.id,
            source_agent_id=r.source_agent_id,
            target_agent_id=r.target_agent_id,
            target_name=name_map.get(r.target_agent_id),
            trust=r.trust,
            warmth=r.warmth,
            respect=r.respect,
            resentment=r.resentment,
            fear=r.fear,
            alliance_active=r.alliance_active,
            grudge_active=r.grudge_active,
        )
        for r in agent.outgoing_relationships
    ]
