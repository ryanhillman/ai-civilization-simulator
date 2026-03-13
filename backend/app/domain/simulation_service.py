"""
SimulationService

Bridges the SQLAlchemy persistence layer and the pure simulation engine.

Conversion flow:
    DB models  ->  WorldState  ->  TurnRunner  ->  TurnResult  ->  DB mutations
"""
from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.enums import ResourceType, Season
from app.models.db import (
    Agent,
    AgentInventory,
    AgentMemory,
    Relationship,
    TurnEvent,
    World,
)
from app.seed_data import AGENTS, RELATIONSHIPS, WORLD_NAME
from app.simulation.pipeline import build_phase3_pipeline
from app.simulation.runner import TurnRunner
from app.simulation.types import (
    AgentState,
    InventorySnapshot,
    MemoryRecord,
    RelationshipState,
    TurnEventRecord,
    TurnResult,
    WorldState,
)


# ---------------------------------------------------------------------------
# DB -> domain
# ---------------------------------------------------------------------------


def _compute_constitution(world_id: int, agent_id: int) -> float:
    """Deterministic metabolic constitution multiplier in [0.85, 1.15].

    Seeded from (world_id, agent_id) via FNV-1a-style 32-bit mixing so each
    world produces a unique metabolism profile for each agent. This breaks the
    fixed Roland/Marta mortality order: Roland might have low constitution
    (eating more) in one world but high constitution (eating less) in another.

    Default agents created without a DB world (tests) get constitution=1.0
    because AgentState.constitution defaults to 1.0 in types.py.
    """
    raw = ((world_id * 2654435761) ^ (agent_id * 40503)) & 0xFFFFFFFF
    return round(0.85 + (raw % 10000) / 33333.0, 3)


def _agent_to_state(agent: Agent) -> AgentState:
    inv = InventorySnapshot()
    for item in agent.inventory:
        inv = inv.adjust(item.resource_type, item.quantity)

    recent_memories = [
        MemoryRecord(
            agent_id=m.agent_id,
            world_id=m.world_id,
            turn_number=m.turn_number,
            event_type=m.event_type,
            summary=m.summary,
            emotional_weight=m.emotional_weight,
            related_agent_id=m.related_agent_id,
        )
        for m in (getattr(agent, "memories", None) or [])
    ]

    return AgentState(
        id=agent.id,
        world_id=agent.world_id,
        name=agent.name,
        profession=agent.profession,
        age=agent.age,
        is_alive=agent.is_alive,
        is_sick=agent.is_sick,
        hunger=agent.hunger,
        constitution=_compute_constitution(agent.world_id, agent.id),
        personality_traits=agent.personality_traits or {},
        goals=agent.goals or [],
        inventory=inv,
        recent_memories=recent_memories,
        consecutive_work_turns=getattr(agent, "consecutive_work_turns", 0) or 0,
        days_sick=getattr(agent, "days_sick", 0) or 0,
        max_health=getattr(agent, "max_health", 1.0) or 1.0,
    )


def _world_to_state(world: World) -> WorldState:
    relationships: list[RelationshipState] = []
    for agent in world.agents:
        for rel in (getattr(agent, "outgoing_relationships", None) or []):
            relationships.append(RelationshipState(
                source_agent_id=rel.source_agent_id,
                target_agent_id=rel.target_agent_id,
                trust=rel.trust,
                warmth=rel.warmth,
                respect=rel.respect,
                resentment=rel.resentment,
                fear=rel.fear,
            ))

    return WorldState(
        id=world.id,
        name=world.name,
        current_turn=world.current_turn,
        current_day=world.current_day,
        current_season=world.current_season,
        weather=world.weather,
        agents=[_agent_to_state(a) for a in world.agents],
        relationships=relationships,
    )


# ---------------------------------------------------------------------------
# DB load
# ---------------------------------------------------------------------------


async def _load_world(world_id: int, session: AsyncSession) -> World:
    stmt = (
        select(World)
        .where(World.id == world_id)
        .options(
            selectinload(World.agents).options(
                selectinload(Agent.inventory),
                selectinload(Agent.memories),
                selectinload(Agent.outgoing_relationships),
            )
        )
    )
    result = await session.execute(stmt)
    world = result.scalar_one_or_none()
    if world is None:
        raise ValueError(f"World {world_id} not found")
    return world


# ---------------------------------------------------------------------------
# Domain -> DB mutations
# ---------------------------------------------------------------------------


async def _persist_turn_results(
    world: World,
    results: list[TurnResult],
    session: AsyncSession,
) -> None:
    """Apply a sequence of TurnResults to the DB.

    Agent states are updated from the final result; events and memories are
    inserted from all results.
    """
    if not results:
        return

    final = results[-1]
    final_ws = final.world_state

    # 1. Update world
    world.current_turn = final_ws.current_turn
    world.current_day = final_ws.current_day
    world.current_season = final_ws.current_season
    world.weather = final_ws.weather

    # 2. Update agents + inventories
    agent_map = {a.id: a for a in world.agents}
    for agent_state in final_ws.agents:
        db_agent = agent_map.get(agent_state.id)
        if db_agent is None:
            continue
        db_agent.hunger = agent_state.hunger
        db_agent.is_alive = agent_state.is_alive
        db_agent.is_sick = agent_state.is_sick
        db_agent.consecutive_work_turns = agent_state.consecutive_work_turns
        db_agent.days_sick = agent_state.days_sick
        db_agent.max_health = agent_state.max_health

        inv_map = {item.resource_type: item for item in db_agent.inventory}
        for resource in ResourceType:
            qty = agent_state.inventory.get(resource)
            if resource in inv_map:
                inv_map[resource].quantity = qty
            else:
                session.add(AgentInventory(
                    agent_id=db_agent.id,
                    resource_type=resource,
                    quantity=qty,
                ))

    # 3. Upsert relationships from final world state
    agent_ids = list(agent_map.keys())
    rel_stmt = select(Relationship).where(
        Relationship.source_agent_id.in_(agent_ids)
    )
    rel_result = await session.execute(rel_stmt)
    rel_map = {
        (r.source_agent_id, r.target_agent_id): r
        for r in rel_result.scalars().all()
    }
    for rel_state in final_ws.relationships:
        key = (rel_state.source_agent_id, rel_state.target_agent_id)
        if key in rel_map:
            db_rel = rel_map[key]
            db_rel.trust = rel_state.trust
            db_rel.warmth = rel_state.warmth
            db_rel.respect = rel_state.respect
            db_rel.resentment = rel_state.resentment
            db_rel.fear = rel_state.fear
            db_rel.alliance_active = rel_state.alliance_active
            db_rel.grudge_active = rel_state.grudge_active
        else:
            session.add(Relationship(
                source_agent_id=rel_state.source_agent_id,
                target_agent_id=rel_state.target_agent_id,
                trust=rel_state.trust,
                warmth=rel_state.warmth,
                respect=rel_state.respect,
                resentment=rel_state.resentment,
                fear=rel_state.fear,
                alliance_active=rel_state.alliance_active,
                grudge_active=rel_state.grudge_active,
            ))

    # 4. Insert TurnEvents from all results
    for result in results:
        for record in result.events:
            session.add(_build_turn_event(record))

    # 5. Insert AgentMemories from all results
    for result in results:
        for record in result.memories:
            session.add(_build_memory(record))


def _build_turn_event(record: TurnEventRecord) -> TurnEvent:
    return TurnEvent(
        world_id=record.world_id,
        turn_number=record.turn_number,
        event_type=record.event_type,
        description=record.description,
        agent_ids=record.agent_ids,
        details=record.details,
    )


def _build_memory(record: MemoryRecord) -> AgentMemory:
    return AgentMemory(
        agent_id=record.agent_id,
        world_id=record.world_id,
        turn_number=record.turn_number,
        event_type=record.event_type,
        summary=record.summary,
        emotional_weight=record.emotional_weight,
        related_agent_id=record.related_agent_id,
    )


# Public aliases kept for backward compatibility (hardening tests import these names)
agent_to_state = _agent_to_state
world_to_state = _world_to_state
build_turn_event = _build_turn_event
build_memory = _build_memory


# ---------------------------------------------------------------------------
# Seeding helper (shared by seed script and reset endpoint)
# ---------------------------------------------------------------------------


async def seed_world(session: AsyncSession, world_name: str = WORLD_NAME) -> World:
    """Create a fresh world with the Ashenvale seed data. Returns the new World."""
    world = World(name=world_name)
    session.add(world)
    await session.flush()

    agent_map: dict[str, Agent] = {}
    for agent_data in AGENTS:
        inv = agent_data["inventory"]
        db_agent = Agent(
            world_id=world.id,
            name=agent_data["name"],
            profession=agent_data["profession"],
            age=agent_data["age"],
            personality_traits=agent_data["personality_traits"],
            goals=agent_data["goals"],
        )
        session.add(db_agent)
        await session.flush()

        for resource_type, quantity in inv.items():
            session.add(AgentInventory(
                agent_id=db_agent.id,
                resource_type=resource_type,
                quantity=quantity,
            ))

        agent_map[agent_data["name"]] = db_agent

    await session.flush()

    for (src, tgt, trust, warmth, respect, resentment, fear) in RELATIONSHIPS:
        session.add(Relationship(
            source_agent_id=agent_map[src].id,
            target_agent_id=agent_map[tgt].id,
            trust=trust,
            warmth=warmth,
            respect=respect,
            resentment=resentment,
            fear=fear,
            alliance_active=(trust >= 0.6 and warmth >= 0.4),
            grudge_active=(resentment >= 0.6 or fear >= 0.5),
        ))

    await session.flush()
    return world


# ---------------------------------------------------------------------------
# High-level service (async DB I/O)
# ---------------------------------------------------------------------------


class SimulationService:
    """High-level facade used by API route handlers."""

    def __init__(self, runner: TurnRunner | None = None) -> None:
        self._runner = runner or TurnRunner(pipeline=build_phase3_pipeline())

    async def advance_turn(self, world_id: int, session: AsyncSession) -> TurnResult:
        """Load world, run one turn, persist, return TurnResult."""
        world = await _load_world(world_id, session)
        world_state = _world_to_state(world)

        from app.core.config import settings
        if settings.ai_enabled:
            result = await self._advance_turn_with_ai(world, world_state, session)
        else:
            result = self._runner.run_turn(world_state)
            await _persist_turn_results(world, [result], session)
        return result

    async def _advance_turn_with_ai(
        self,
        world,
        world_state,
        session: AsyncSession,
    ) -> TurnResult:
        """
        Run one turn with optional AI decision support.

        Splits the pipeline at economy_opportunities:
          1. Run stages up to economy_opportunities → generates scored candidates.
          2. Ask AI for decision hints on ambiguous agents (bounded by config).
          3. Inject validated hints into pre_selected_actions.
          4. Continue from resolve_actions onwards.

        Falls back transparently if AI fails — the deterministic pipeline still runs.
        """
        from app.ai.service import ai_service
        from app.simulation.types import TurnContext
        from app.simulation.runner import build_turn_summary

        pipeline = self._runner.pipeline

        # Bump turn counter (mirrors what TurnRunner does internally)
        bumped = world_state.model_copy(
            update={"current_turn": world_state.current_turn + 1}
        )
        ctx = TurnContext(world_state=bumped)

        # Phase 1: run deterministic stages up through opportunity generation
        ctx = pipeline.run_up_to("economy_opportunities", ctx)

        # Phase 2: optional AI decision hints (non-blocking failure)
        name_map: dict[int, str] = {a.id: a.name for a in world.agents}
        try:
            hints = await ai_service.advise_decisions(ctx, name_map)
            if hints:
                ctx = ctx.model_copy(update={"pre_selected_actions": hints})
        except Exception:
            pass  # decision support failure is fully transparent

        # Phase 3: continue deterministic pipeline from resolve_actions
        ctx = pipeline.run_from("resolve_actions", ctx)

        summary = build_turn_summary(ctx.events)
        result = TurnResult(
            world_id=world_state.id,
            turn_number=bumped.current_turn,
            world_state=ctx.world_state,
            resolved_actions=ctx.resolved_actions,
            events=ctx.events,
            memories=ctx.memories,
            pressures=ctx.pressures,
            world_events=ctx.world_events,
            summary=summary,
        )
        await _persist_turn_results(world, [result], session)
        return result

    async def advance_turns(
        self, world_id: int, n: int, session: AsyncSession
    ) -> list[TurnResult]:
        """Run n turns sequentially (in memory), persist all, return list."""
        world = await _load_world(world_id, session)
        world_state = _world_to_state(world)
        results = self._runner.run_turns(world_state, n=n)
        await _persist_turn_results(world, results, session)
        return results

    async def reset_world(self, world_id: int, session: AsyncSession) -> World:
        """Reset the world in-place to the seeded baseline. The world ID stays the same."""
        world = await _load_world(world_id, session)

        # 1. Reset world-level state fields
        world.current_turn = 0
        world.current_day = 1
        world.current_season = Season.spring
        world.weather = "clear"

        # 2. Delete all agents — cascade removes inventory, memories, relationships
        for agent in list(world.agents):
            await session.delete(agent)

        # 3. Delete all turn_events for this world
        await session.execute(delete(TurnEvent).where(TurnEvent.world_id == world_id))

        await session.flush()

        # 4. Re-seed agents + relationships under the same world_id
        agent_map: dict[str, Agent] = {}
        for agent_data in AGENTS:
            db_agent = Agent(
                world_id=world.id,
                name=agent_data["name"],
                profession=agent_data["profession"],
                age=agent_data["age"],
                personality_traits=agent_data["personality_traits"],
                goals=agent_data["goals"],
            )
            session.add(db_agent)
            await session.flush()

            for resource_type, quantity in agent_data["inventory"].items():
                session.add(AgentInventory(
                    agent_id=db_agent.id,
                    resource_type=resource_type,
                    quantity=quantity,
                ))

            agent_map[agent_data["name"]] = db_agent

        await session.flush()

        for (src, tgt, trust, warmth, respect, resentment, fear) in RELATIONSHIPS:
            session.add(Relationship(
                source_agent_id=agent_map[src].id,
                target_agent_id=agent_map[tgt].id,
                trust=trust,
                warmth=warmth,
                respect=respect,
                resentment=resentment,
                fear=fear,
                alliance_active=(trust >= 0.6 and warmth >= 0.4),
                grudge_active=(resentment >= 0.6 or fear >= 0.5),
            ))

        await session.flush()

        # Expire all stale ORM state so the returned object is fresh
        session.expire(world)
        await session.refresh(world)
        return world

    async def list_worlds(self, session: AsyncSession) -> list[World]:
        result = await session.execute(select(World).order_by(World.id))
        return list(result.scalars().all())

    async def get_world(self, world_id: int, session: AsyncSession) -> World:
        world = await session.get(World, world_id)
        if world is None:
            raise ValueError(f"World {world_id} not found")
        return world

    async def create_world(self, name: str, session: AsyncSession) -> World:
        """Create a new world. If name is WORLD_NAME, seed with village data."""
        if name == WORLD_NAME:
            return await seed_world(session, name)
        world = World(name=name)
        session.add(world)
        await session.flush()
        return world
