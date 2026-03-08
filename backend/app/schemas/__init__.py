"""
Pydantic DTOs for all API request / response bodies.

These schemas sit between the HTTP layer and the domain/DB layer.
They do not import from app.simulation.* or app.models.db directly
(only app.enums for shared vocabulary).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.enums import EventType, Profession, ResourceType, Season


# ---------------------------------------------------------------------------
# World
# ---------------------------------------------------------------------------


class WorldResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    current_turn: int
    current_day: int
    current_season: Season
    weather: str
    created_at: datetime
    updated_at: datetime


class CreateWorldRequest(BaseModel):
    name: str


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


class InventoryResponse(BaseModel):
    food: float = 0.0
    coin: float = 0.0
    wood: float = 0.0
    medicine: float = 0.0


class AgentSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    profession: Profession
    age: int
    is_alive: bool
    is_sick: bool
    hunger: float


class RelationshipResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_agent_id: int
    target_agent_id: int
    target_name: Optional[str] = None
    trust: float
    warmth: float
    respect: float
    resentment: float
    fear: float
    alliance_active: bool
    grudge_active: bool


class MemoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    agent_id: int
    world_id: int
    turn_number: int
    event_type: EventType
    summary: str
    emotional_weight: float
    related_agent_id: Optional[int] = None
    related_agent_name: Optional[str] = None
    visibility: str
    created_at: datetime


class AgentDetailResponse(AgentSummaryResponse):
    personality_traits: dict[str, float] = {}
    goals: list[dict[str, Any]] = []
    inventory: InventoryResponse = Field(default_factory=InventoryResponse)
    relationships: list[RelationshipResponse] = []
    recent_memories: list[MemoryResponse] = []


# ---------------------------------------------------------------------------
# Simulation — turn result
# ---------------------------------------------------------------------------


class AgentPressureResponse(BaseModel):
    agent_id: int
    hunger_pressure: float
    resource_pressure: float
    sickness_pressure: float
    social_pressure: float
    memory_pressure: float
    total: float
    top_reasons: list[str]


class ResolvedActionResponse(BaseModel):
    agent_id: int
    action_type: str
    succeeded: bool
    outcome: str
    details: dict[str, Any] = {}


class TurnEventDomainResponse(BaseModel):
    world_id: int
    turn_number: int
    event_type: str
    description: str
    agent_ids: list[int] = []
    details: dict[str, Any] = {}


class WorldEventResponse(BaseModel):
    event_type: str
    description: str
    affected_agent_ids: list[int] = []
    modifiers: dict[str, Any] = {}


class AgentTurnSummary(BaseModel):
    """Agent state as included in TurnResultResponse (end-of-turn snapshot)."""

    id: int
    name: str
    profession: Profession
    is_alive: bool
    is_sick: bool
    hunger: float
    inventory: InventoryResponse
    pressure: Optional[AgentPressureResponse] = None


class TurnResultResponse(BaseModel):
    world_id: int
    turn_number: int
    current_day: int
    current_season: Season
    weather: str
    agents: list[AgentTurnSummary]
    resolved_actions: list[ResolvedActionResponse]
    events: list[TurnEventDomainResponse]
    world_events: list[WorldEventResponse]
    pressures: list[AgentPressureResponse]
    summary: str


class RunRequest(BaseModel):
    n: int = Field(ge=1, le=100, default=1)


class AutoplayRequest(BaseModel):
    max_turns: int = Field(ge=1, default=10)


# ---------------------------------------------------------------------------
# Timeline
# ---------------------------------------------------------------------------


class TurnEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    world_id: int
    turn_number: int
    event_type: EventType
    description: str
    narrative: Optional[str] = None
    agent_ids: list[int]
    details: dict[str, Any]
    created_at: datetime


# ---------------------------------------------------------------------------
# Helpers: domain → response schema conversion
# ---------------------------------------------------------------------------


def build_inventory_response(items: list) -> InventoryResponse:
    """Convert a list of AgentInventory ORM objects to InventoryResponse."""
    inv: dict[str, float] = {}
    for item in items:
        inv[item.resource_type.value] = item.quantity
    return InventoryResponse(
        food=inv.get("food", 0.0),
        coin=inv.get("coin", 0.0),
        wood=inv.get("wood", 0.0),
        medicine=inv.get("medicine", 0.0),
    )


def build_turn_result_response(result) -> TurnResultResponse:  # type: ignore[type-arg]
    """Convert a TurnResult domain object to TurnResultResponse."""
    from app.simulation.types import TurnResult  # local import avoids circular

    ws = result.world_state
    agents = []
    for a in ws.agents:
        pressure_domain = result.pressures.get(a.id)
        pressure_resp: Optional[AgentPressureResponse] = None
        if pressure_domain:
            pressure_resp = AgentPressureResponse(
                agent_id=pressure_domain.agent_id,
                hunger_pressure=pressure_domain.hunger_pressure,
                resource_pressure=pressure_domain.resource_pressure,
                sickness_pressure=pressure_domain.sickness_pressure,
                social_pressure=pressure_domain.social_pressure,
                memory_pressure=pressure_domain.memory_pressure,
                total=pressure_domain.total,
                top_reasons=pressure_domain.top_reasons,
            )
        agents.append(AgentTurnSummary(
            id=a.id,
            name=a.name,
            profession=a.profession,
            is_alive=a.is_alive,
            is_sick=a.is_sick,
            hunger=a.hunger,
            inventory=InventoryResponse(
                food=a.inventory.food,
                coin=a.inventory.coin,
                wood=a.inventory.wood,
                medicine=a.inventory.medicine,
            ),
            pressure=pressure_resp,
        ))

    return TurnResultResponse(
        world_id=result.world_id,
        turn_number=result.turn_number,
        current_day=ws.current_day,
        current_season=ws.current_season,
        weather=ws.weather,
        agents=agents,
        resolved_actions=[
            ResolvedActionResponse(
                agent_id=a.agent_id,
                action_type=a.action_type,
                succeeded=a.succeeded,
                outcome=a.outcome,
                details=a.details,
            )
            for a in result.resolved_actions
        ],
        events=[
            TurnEventDomainResponse(
                world_id=e.world_id,
                turn_number=e.turn_number,
                event_type=e.event_type.value,
                description=e.description,
                agent_ids=e.agent_ids,
                details=e.details,
            )
            for e in result.events
        ],
        world_events=[
            WorldEventResponse(
                event_type=we.event_type,
                description=we.description,
                affected_agent_ids=we.affected_agent_ids,
                modifiers=we.modifiers,
            )
            for we in result.world_events
        ],
        pressures=[
            AgentPressureResponse(
                agent_id=p.agent_id,
                hunger_pressure=p.hunger_pressure,
                resource_pressure=p.resource_pressure,
                sickness_pressure=p.sickness_pressure,
                social_pressure=p.social_pressure,
                memory_pressure=p.memory_pressure,
                total=p.total,
                top_reasons=p.top_reasons,
            )
            for p in result.pressures.values()
        ],
        summary=result.summary,
    )
