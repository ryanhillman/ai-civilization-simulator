"""
Stage 3 — Opportunity Generation

Generates the set of actions each living agent may take this turn.
An Opportunity is a candidate action; actual selection happens in Stage 4.

Phase 3 changes
---------------
- Each generated opportunity is scored via pressure.score_opportunity().
  Opportunities generated when ctx.pressures is empty (Phase 2 pipeline)
  receive a baseline score of 1.0.
- Harvest yield is multiplied by any active world-event modifier
  (poor_harvest, storm) read from ctx.world_events.
- High-pressure agents (total >= 3.0) gain a steal_food opportunity
  targeting the agent with the most food in the village.

Extension points
----------------
- Economy engine: inject market-trade opportunities after this stage
- Social engine: inject alliance/gift/gossip opportunities
- LLM integration (Phase 6+): LLM will choose among scored opportunities;
  Stage 4 currently selects deterministically by score.
"""
from __future__ import annotations

from app.enums import Profession
from app.simulation.pressure import score_opportunity
from app.simulation.types import (
    AgentPressure,
    AgentState,
    Opportunity,
    TurnContext,
    WorldEventRecord,
)

# ---------------------------------------------------------------------------
# Harvest modifier helper
# ---------------------------------------------------------------------------


def _harvest_multiplier(world_events: list[WorldEventRecord]) -> float:
    """Return the lowest harvest_yield_multiplier from active world events."""
    multiplier = 1.0
    for we in world_events:
        m = we.modifiers.get("harvest_yield_multiplier")
        if m is not None:
            multiplier = min(multiplier, float(m))
    return multiplier


def _patrol_blocked(world_events: list[WorldEventRecord]) -> bool:
    return any(we.modifiers.get("patrol_blocked") for we in world_events)


# ---------------------------------------------------------------------------
# Per-profession opportunity builders
# ---------------------------------------------------------------------------


def _profession_opportunities(
    agent: AgentState,
    all_agents: list[AgentState],
    world_events: list[WorldEventRecord],
) -> list[Opportunity]:
    aid = agent.id
    opps: list[Opportunity] = []

    # Universal: every agent can rest
    opps.append(Opportunity(agent_id=aid, action_type="rest"))

    profession = agent.profession
    harvest_mult = _harvest_multiplier(world_events)

    if profession == Profession.farmer:
        opps.append(Opportunity(
            agent_id=aid,
            action_type="harvest_food",
            metadata={"yield_base": round(3.0 * harvest_mult, 4)},
        ))

    elif profession == Profession.blacksmith:
        if agent.inventory.wood >= 2.0:
            opps.append(Opportunity(
                agent_id=aid,
                action_type="craft_tools",
                metadata={"wood_cost": 2.0, "coin_gain": 5.0},
            ))

    elif profession == Profession.merchant:
        opps.append(Opportunity(
            agent_id=aid,
            action_type="trade_goods",
            metadata={"coin_gain_base": 3.0},
        ))

    elif profession == Profession.healer:
        if agent.is_sick and agent.inventory.medicine >= 1.0:
            opps.append(Opportunity(
                agent_id=aid,
                action_type="heal_self",
                metadata={"medicine_cost": 1.0},
            ))
        # Heal up to 2 sick agents per turn
        sick_others = [
            a for a in all_agents
            if a.id != aid and a.is_alive and a.is_sick
        ]
        for sick in sick_others[:2]:
            if agent.inventory.medicine >= 1.0:
                opps.append(Opportunity(
                    agent_id=aid,
                    action_type="heal_agent",
                    target_agent_id=sick.id,
                    metadata={"medicine_cost": 1.0},
                ))

    elif profession == Profession.priest:
        opps.append(Opportunity(agent_id=aid, action_type="pray"))
        opps.append(Opportunity(agent_id=aid, action_type="bless_village"))

    elif profession == Profession.soldier:
        if not _patrol_blocked(world_events):
            opps.append(Opportunity(agent_id=aid, action_type="patrol"))

    return opps


def _steal_food_opportunity(
    agent: AgentState,
    all_agents: list[AgentState],
    pressure: AgentPressure,
) -> Opportunity | None:
    """
    Desperate agents (total pressure >= 3.0) may steal food.

    Target is the agent with the most food who is not the actor.
    Only generated if a meaningful target (food >= 2.0) exists.
    """
    if pressure.total < 3.0:
        return None
    candidates = [
        a for a in all_agents
        if a.id != agent.id and a.inventory.food >= 2.0
    ]
    if not candidates:
        return None
    target = max(candidates, key=lambda a: a.inventory.food)
    return Opportunity(
        agent_id=agent.id,
        action_type="steal_food",
        target_agent_id=target.id,
        metadata={"steal_amount": 2.0, "target_id": target.id},
    )


# ---------------------------------------------------------------------------
# Stage entry point
# ---------------------------------------------------------------------------


def generate_opportunities(ctx: TurnContext) -> TurnContext:
    """
    Generate all profession opportunities for living agents.

    Each opportunity is scored using the agent's pressure profile from
    ctx.pressures. Opportunities generated before compute_pressure has run
    (e.g. Phase 2 pipeline) receive a baseline score of 1.0.

    Extension points:
    - economy_opportunities (inserted after this stage) adds trade opps
    - social_opportunities (inserted after economy) adds gossip/gift opps
    """
    all_agents = ctx.world_state.living_agents
    opps: list[Opportunity] = []

    for agent in all_agents:
        pressure = ctx.pressures.get(agent.id)
        raw_opps = _profession_opportunities(agent, all_agents, ctx.world_events)

        # Add steal opportunity for desperate agents
        steal = _steal_food_opportunity(agent, all_agents, pressure) if pressure else None
        if steal:
            raw_opps.append(steal)

        scored_opps = [score_opportunity(o, pressure) for o in raw_opps]
        opps.extend(scored_opps)

    return ctx.model_copy(update={"opportunities": opps})
