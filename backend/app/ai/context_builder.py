"""
Context builder for the AI service layer.

Two entry points:
  build_agent_context_from_orm()   — used in API routes (has ORM models)
  build_agent_context_from_state() — used in SimulationService (has domain types)

Both produce an AgentContextData that feeds directly into prompt formatters.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.ai.schemas import AgentContextData

if TYPE_CHECKING:
    from app.simulation.types import AgentState, WorldState


# ---------------------------------------------------------------------------
# From ORM models (API route path)
# ---------------------------------------------------------------------------


def build_agent_context_from_orm(
    agent,          # app.models.db.Agent (with inventory, memories, outgoing_relationships loaded)
    world,          # app.models.db.World
    name_map: dict[int, str],
) -> AgentContextData:
    """Build compact AI context from SQLAlchemy ORM model instances."""
    rels = sorted(
        getattr(agent, "outgoing_relationships", None) or [],
        key=lambda r: abs(r.trust),
        reverse=True,
    )[:3]

    rel_summaries: list[dict[str, Any]] = []
    for r in rels:
        target_name = name_map.get(r.target_agent_id, f"Agent#{r.target_agent_id}")
        status = (
            "ally" if getattr(r, "alliance_active", False)
            else "foe" if getattr(r, "grudge_active", False)
            else "acquaintance"
        )
        rel_summaries.append({
            "name": target_name,
            "status": status,
            "trust": round(r.trust, 2),
            "warmth": round(r.warmth, 2),
        })

    memories = sorted(
        getattr(agent, "memories", None) or [],
        key=lambda m: m.turn_number,
    )[-5:]
    mem_summaries = [m.summary for m in memories]

    hunger = float(getattr(agent, "hunger", 0.0))
    pressure_reasons: list[str] = []
    if hunger > 0.5:
        pressure_reasons.append(f"very hungry ({int(hunger * 100)}%)")
    elif hunger > 0.25:
        pressure_reasons.append(f"hungry ({int(hunger * 100)}%)")
    if getattr(agent, "is_sick", False):
        pressure_reasons.append("ill")

    traits = dict(getattr(agent, "personality_traits", None) or {})
    goals = list(getattr(agent, "goals", None) or [])
    goal_summaries = [
        {"type": g.get("type", ""), "target": g.get("target", "")}
        for g in goals
    ]

    world_name = getattr(world, "name", "the village")
    season = world.current_season.value if hasattr(world.current_season, "value") else str(world.current_season)
    weather = getattr(world, "weather", "clear")

    return AgentContextData(
        agent_id=agent.id,
        agent_name=agent.name,
        profession=agent.profession.value if hasattr(agent.profession, "value") else str(agent.profession),
        age=agent.age,
        traits=traits,
        goals=goal_summaries,
        relationships=rel_summaries,
        recent_memories=mem_summaries,
        hunger_pct=int(hunger * 100),
        pressure_reasons=pressure_reasons,
        season=season,
        weather=weather,
        world_name=world_name,
        is_alive=bool(getattr(agent, "is_alive", True)),
    )


# ---------------------------------------------------------------------------
# From simulation domain types (SimulationService path)
# ---------------------------------------------------------------------------


def build_agent_context_from_state(
    agent: "AgentState",
    world_state: "WorldState",
    name_map: dict[int, str],
) -> AgentContextData:
    """Build compact AI context from pure simulation domain objects."""
    agent_rels = [
        r for r in world_state.relationships
        if r.source_agent_id == agent.id
    ]
    agent_rels_sorted = sorted(agent_rels, key=lambda r: abs(r.trust), reverse=True)[:3]

    rel_summaries: list[dict[str, Any]] = []
    for r in agent_rels_sorted:
        target_name = name_map.get(r.target_agent_id, f"Agent#{r.target_agent_id}")
        status = "ally" if r.alliance_active else "foe" if r.grudge_active else "acquaintance"
        rel_summaries.append({
            "name": target_name,
            "status": status,
            "trust": round(r.trust, 2),
            "warmth": round(r.warmth, 2),
        })

    mem_summaries = [m.summary for m in agent.recent_memories[-5:]]

    pressure_reasons: list[str] = []
    if agent.hunger > 0.5:
        pressure_reasons.append(f"very hungry ({int(agent.hunger * 100)}%)")
    elif agent.hunger > 0.25:
        pressure_reasons.append(f"hungry ({int(agent.hunger * 100)}%)")
    if agent.is_sick:
        pressure_reasons.append("ill")

    goal_summaries = [
        {"type": g.get("type", ""), "target": g.get("target", "")}
        for g in agent.goals
    ]

    return AgentContextData(
        agent_id=agent.id,
        agent_name=agent.name,
        profession=agent.profession.value,
        age=agent.age,
        traits=dict(agent.personality_traits),
        goals=goal_summaries,
        relationships=rel_summaries,
        recent_memories=mem_summaries,
        hunger_pct=int(agent.hunger * 100),
        pressure_reasons=pressure_reasons,
        season=world_state.current_season.value,
        weather=world_state.weather,
        world_name=world_state.name,
        is_alive=agent.is_alive,
    )
