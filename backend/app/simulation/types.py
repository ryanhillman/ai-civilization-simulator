"""
Pure domain value objects for the simulation engine.

No SQLAlchemy, no DB connections, no I/O.
These types flow through the turn pipeline and are converted to/from DB
models by the SimulationService (app/domain/simulation_service.py).
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from app.enums import EventType, Profession, ResourceType, Season


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------


class InventorySnapshot(BaseModel):
    """Immutable resource holdings for a single agent."""

    food: float = 0.0
    coin: float = 0.0
    wood: float = 0.0
    medicine: float = 0.0

    def get(self, resource: ResourceType) -> float:
        return getattr(self, resource.value, 0.0)

    def adjust(self, resource: ResourceType, delta: float) -> "InventorySnapshot":
        """Return a new snapshot with resource adjusted by delta (floored at 0)."""
        current = self.get(resource)
        new_val = max(0.0, round(current + delta, 4))
        return self.model_copy(update={resource.value: new_val})


# ---------------------------------------------------------------------------
# Agent / World state
# ---------------------------------------------------------------------------


class AgentState(BaseModel):
    """Snapshot of a single agent at the start of a turn."""

    id: int
    world_id: int
    name: str
    profession: Profession
    age: int
    is_alive: bool = True
    is_sick: bool = False
    hunger: float = 0.0  # 0.0 = full, 1.0 = starving/dead threshold
    personality_traits: dict[str, float] = Field(default_factory=dict)
    goals: list[dict[str, Any]] = Field(default_factory=list)
    inventory: InventorySnapshot = Field(default_factory=InventorySnapshot)


class WorldState(BaseModel):
    """Complete world snapshot passed into and produced by each turn."""

    id: int
    name: str
    current_turn: int
    current_day: int
    current_season: Season
    weather: str
    agents: list[AgentState]

    @property
    def living_agents(self) -> list[AgentState]:
        return [a for a in self.agents if a.is_alive]

    def agent_by_id(self, agent_id: int) -> Optional[AgentState]:
        for a in self.agents:
            if a.id == agent_id:
                return a
        return None


# ---------------------------------------------------------------------------
# Opportunities and actions
# ---------------------------------------------------------------------------


class Opportunity(BaseModel):
    """A possible action available to an agent this turn."""

    agent_id: int
    action_type: str
    target_agent_id: Optional[int] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ResolvedAction(BaseModel):
    """The outcome of an agent executing an action this turn."""

    agent_id: int
    action_type: str
    succeeded: bool = True
    outcome: str = ""
    details: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Turn outputs
# ---------------------------------------------------------------------------


class TurnEventRecord(BaseModel):
    """A single event that occurred this turn (persisted as TurnEvent in DB)."""

    world_id: int
    turn_number: int
    event_type: EventType
    description: str
    agent_ids: list[int] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)


class MemoryRecord(BaseModel):
    """A memory to store for an agent (persisted as AgentMemory in DB)."""

    agent_id: int
    world_id: int
    turn_number: int
    event_type: EventType
    summary: str
    emotional_weight: float = 0.0  # -1.0 (traumatic) to 1.0 (joyful)
    related_agent_id: Optional[int] = None


class TurnResult(BaseModel):
    """
    Complete structured output of a single turn execution.

    This is the contract between the simulation engine and the outside world
    (API layer, persistence layer, frontend via JSON).
    """

    world_id: int
    turn_number: int
    world_state: WorldState
    resolved_actions: list[ResolvedAction] = Field(default_factory=list)
    events: list[TurnEventRecord] = Field(default_factory=list)
    memories: list[MemoryRecord] = Field(default_factory=list)
    summary: str = ""


# ---------------------------------------------------------------------------
# Pipeline working context
# ---------------------------------------------------------------------------


class TurnContext(BaseModel):
    """
    Mutable working context threaded through all pipeline stages.

    Each stage receives a TurnContext, applies its logic, and returns a new
    TurnContext (immutable update pattern via model_copy).
    """

    world_state: WorldState
    opportunities: list[Opportunity] = Field(default_factory=list)
    resolved_actions: list[ResolvedAction] = Field(default_factory=list)
    events: list[TurnEventRecord] = Field(default_factory=list)
    memories: list[MemoryRecord] = Field(default_factory=list)
