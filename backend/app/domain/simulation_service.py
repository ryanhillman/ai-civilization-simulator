"""
SimulationService

Bridges the SQLAlchemy persistence layer and the pure simulation engine.

Phase 2: conversion helpers only (load_world_state, apply_turn_result).
Database I/O stubs are marked TODO for Phase 3, when the API routes are wired up.

Conversion flow:
    DB models  →  WorldState  →  TurnRunner  →  TurnResult  →  DB mutations
"""
from __future__ import annotations

from app.models.db import (
    Agent,
    AgentInventory,
    AgentMemory,
    TurnEvent,
    World,
)
from app.simulation.runner import TurnRunner
from app.simulation.types import (
    AgentState,
    InventorySnapshot,
    MemoryRecord,
    TurnEventRecord,
    TurnResult,
    WorldState,
)


# ---------------------------------------------------------------------------
# DB → domain
# ---------------------------------------------------------------------------


def agent_to_state(agent: Agent) -> AgentState:
    """Convert a loaded Agent ORM object (with inventory) to AgentState."""
    inv = InventorySnapshot()
    for item in agent.inventory:
        inv = inv.adjust(item.resource_type, item.quantity)
    return AgentState(
        id=agent.id,
        world_id=agent.world_id,
        name=agent.name,
        profession=agent.profession,
        age=agent.age,
        is_alive=agent.is_alive,
        is_sick=agent.is_sick,
        hunger=agent.hunger,
        personality_traits=agent.personality_traits or {},
        goals=agent.goals or [],
        inventory=inv,
    )


def world_to_state(world: World) -> WorldState:
    """
    Convert a loaded World ORM object (with agents + inventory eagerly loaded)
    to a WorldState domain object.
    """
    return WorldState(
        id=world.id,
        name=world.name,
        current_turn=world.current_turn,
        current_day=world.current_day,
        current_season=world.current_season,
        weather=world.weather,
        agents=[agent_to_state(a) for a in world.agents],
    )


# ---------------------------------------------------------------------------
# Domain → DB mutations
# ---------------------------------------------------------------------------


def build_turn_event(record: TurnEventRecord) -> TurnEvent:
    """Create an unsaved TurnEvent ORM object from a TurnEventRecord."""
    return TurnEvent(
        world_id=record.world_id,
        turn_number=record.turn_number,
        event_type=record.event_type,
        description=record.description,
        agent_ids=record.agent_ids,
        details=record.details,
    )


def build_memory(record: MemoryRecord) -> AgentMemory:
    """Create an unsaved AgentMemory ORM object from a MemoryRecord."""
    return AgentMemory(
        agent_id=record.agent_id,
        world_id=record.world_id,
        turn_number=record.turn_number,
        event_type=record.event_type,
        summary=record.summary,
        emotional_weight=record.emotional_weight,
        related_agent_id=record.related_agent_id,
    )


# ---------------------------------------------------------------------------
# High-level service (async DB I/O — Phase 3+)
# ---------------------------------------------------------------------------


class SimulationService:
    """
    High-level façade used by API route handlers.

    Phase 2: methods are stubs — they show the intended interface and the
    conversion pattern, but do not yet execute DB queries.
    Phase 3: replace TODO stubs with real async SQLAlchemy calls.
    """

    def __init__(self, runner: TurnRunner | None = None) -> None:
        self._runner = runner or TurnRunner()

    async def advance_turn(self, world_id: int, session) -> TurnResult:  # type: ignore[type-arg]
        """
        Load world from DB, run one turn, persist results, return TurnResult.

        TODO (Phase 3): implement DB load and write.
        """
        raise NotImplementedError("DB integration deferred to Phase 3")

    async def advance_turns(
        self, world_id: int, n: int, session  # type: ignore[type-arg]
    ) -> list[TurnResult]:
        """
        Run n turns sequentially, persisting after each.

        TODO (Phase 3): implement DB load and write loop.
        """
        raise NotImplementedError("DB integration deferred to Phase 3")
