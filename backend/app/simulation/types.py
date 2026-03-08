"""
Pure domain value objects for the simulation engine.

No SQLAlchemy, no DB connections, no I/O.
These types flow through the turn pipeline and are converted to/from DB
models by the SimulationService (app/domain/simulation_service.py).

Phase 3 additions
-----------------
  RelationshipState  — directed relationship snapshot between two agents
  AgentPressure      — per-turn deterministic pressure breakdown
  RumorRecord        — structured gossip propagated through agent networks
  WorldEventRecord   — world-level event (festival, storm, outbreak, etc.)
  WorldState         — extended with relationships + active_rumors
  AgentState         — extended with recent_memories
  Opportunity        — extended with score field
  TurnResult         — extended with pressures + world_events for inspection
  TurnContext        — extended with pressures + world_events
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
# MemoryRecord — defined early so AgentState can reference it
# ---------------------------------------------------------------------------


class MemoryRecord(BaseModel):
    """A memory to store for an agent (persisted as AgentMemory in DB)."""

    agent_id: int
    world_id: int
    turn_number: int
    event_type: EventType
    summary: str
    emotional_weight: float = 0.0  # -1.0 (traumatic) to 1.0 (joyful)
    related_agent_id: Optional[int] = None


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
    # Recent memories passed in by the service layer; used for memory_pressure.
    # Empty by default so the pure engine works without a DB.
    recent_memories: list[MemoryRecord] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Relationship
# ---------------------------------------------------------------------------


class RelationshipState(BaseModel):
    """
    Directed relationship snapshot: how source_agent perceives target_agent.

    All trust/warmth/respect dimensions: -1.0 (negative) to 1.0 (positive).
    Resentment and fear: 0.0 (none) to 1.0 (extreme).
    Alliance and grudge are derived, not stored.
    """

    source_agent_id: int
    target_agent_id: int
    trust: float = 0.0
    warmth: float = 0.0
    respect: float = 0.0
    resentment: float = 0.0  # 0..1
    fear: float = 0.0        # 0..1

    @property
    def alliance_active(self) -> bool:
        """Alliance: mutual trust >= 0.6 and warmth >= 0.4."""
        return self.trust >= 0.6 and self.warmth >= 0.4

    @property
    def grudge_active(self) -> bool:
        """Grudge: extreme resentment or fear."""
        return self.resentment >= 0.6 or self.fear >= 0.5


# ---------------------------------------------------------------------------
# Agent Pressure
# ---------------------------------------------------------------------------


class AgentPressure(BaseModel):
    """
    Deterministic per-turn pressure profile for a single agent.

    Pressure connects economy, health, social tension, and memory through
    one inspectable mechanism. It influences opportunity scoring and
    action selection without introducing any randomness.

    Total can exceed 1.0 when multiple domains are under stress simultaneously.
    """

    agent_id: int
    hunger_pressure: float = 0.0     # 0..1  — direct from agent.hunger
    resource_pressure: float = 0.0   # 0..1  — food/coin scarcity vs. needs
    sickness_pressure: float = 0.0   # 0..1  — illness burden (0.8 if sick)
    social_pressure: float = 0.0     # 0..1  — incoming resentment / grudges
    memory_pressure: float = 0.0     # 0..1  — recent traumatic memories
    total: float = 0.0               # sum of all five components
    top_reasons: list[str] = Field(default_factory=list)  # human-readable


# ---------------------------------------------------------------------------
# Rumor
# ---------------------------------------------------------------------------


class RumorRecord(BaseModel):
    """
    Structured gossip propagated through agent social networks.

    Rumors are created from notable events (theft, conflict, hoarding,
    sickness) and spread between agents who share high trust. They persist
    in WorldState.active_rumors until turn_expires, then are pruned.
    """

    source_agent_id: int       # who originated the rumor
    subject_agent_id: int      # who the rumor is about
    world_id: int
    turn_created: int
    turn_expires: int          # pruned after this turn
    rumor_type: str            # "theft" | "conflict" | "hoarding" | "sickness"
    content: str               # templated human-readable text
    credibility: float = 0.5   # 0..1 — believability
    spread_count: int = 0
    known_by: list[int] = Field(default_factory=list)  # agent IDs


# ---------------------------------------------------------------------------
# World Event Record
# ---------------------------------------------------------------------------


class WorldEventRecord(BaseModel):
    """
    A world-level event that affects all or some agents for one turn.

    Events are computed deterministically from season, day, turn number,
    and weather. Modifiers are consumed by downstream stages (opportunity
    generation, action resolution).
    """

    event_type: str            # "festival" | "poor_harvest" | "storm" | "sickness_outbreak"
    description: str
    affected_agent_ids: list[int] = Field(default_factory=list)
    modifiers: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# WorldState
# ---------------------------------------------------------------------------


class WorldState(BaseModel):
    """Complete world snapshot passed into and produced by each turn."""

    id: int
    name: str
    current_turn: int
    current_day: int
    current_season: Season
    weather: str
    agents: list[AgentState]
    relationships: list[RelationshipState] = Field(default_factory=list)
    active_rumors: list[RumorRecord] = Field(default_factory=list)

    @property
    def living_agents(self) -> list[AgentState]:
        return [a for a in self.agents if a.is_alive]

    def agent_by_id(self, agent_id: int) -> Optional[AgentState]:
        for a in self.agents:
            if a.id == agent_id:
                return a
        return None

    def relationship(
        self, source_id: int, target_id: int
    ) -> Optional[RelationshipState]:
        for r in self.relationships:
            if r.source_agent_id == source_id and r.target_agent_id == target_id:
                return r
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
    # Deterministic score assigned by the pressure system. Higher = more
    # attractive under current pressure conditions. Baseline is 1.0.
    score: float = 0.0


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


class TurnResult(BaseModel):
    """
    Complete structured output of a single turn execution.

    This is the contract between the simulation engine and the outside world
    (API layer, persistence layer, frontend via JSON).

    Phase 3 additions:
      pressures    — per-agent pressure breakdown for debugging / LLM context
      world_events — world-level events that fired this turn
    """

    world_id: int
    turn_number: int
    world_state: WorldState
    resolved_actions: list[ResolvedAction] = Field(default_factory=list)
    events: list[TurnEventRecord] = Field(default_factory=list)
    memories: list[MemoryRecord] = Field(default_factory=list)
    pressures: dict[int, AgentPressure] = Field(default_factory=dict)
    world_events: list[WorldEventRecord] = Field(default_factory=list)
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
    # Phase 3: pressure profiles computed once per turn, consumed by later stages
    pressures: dict[int, AgentPressure] = Field(default_factory=dict)
    # Phase 3: world-level events fired this turn (festival, storm, outbreak…)
    world_events: list[WorldEventRecord] = Field(default_factory=list)
