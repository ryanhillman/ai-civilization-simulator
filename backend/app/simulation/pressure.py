"""
Agent Pressure System — Phase 3

Computes a deterministic per-turn pressure score for each agent.

Pressure is the single mechanism that connects economy, health, social
tension, and memory. It is computed from current world state only — no
randomness, no LLM, no hidden side effects.

Components
----------
  hunger_pressure   direct from agent.hunger (0..1)
  resource_pressure food/coin scarcity relative to profession needs (0..1)
  sickness_pressure illness burden — 0.8 if sick, 0.0 otherwise
  social_pressure   incoming resentment and active grudges (0..1)
  memory_pressure   weighted sum of recent traumatic memories (0..1)

Total = sum of all five. Can exceed 1.0 under multi-domain stress.

Pressure Effects (via score_opportunity)
-----------------------------------------
  high hunger_pressure    → +score on food-seeking actions
  high resource_pressure  → +score on production / trade
  high sickness_pressure  → +score on healing actions
  high social_pressure    → -score on cooperative actions, +score on stress release
  high total (>= 2.5)     → survival override: score becomes primary selector
  low total  (<  0.5)     → +score on cooperative / generous actions
"""
from __future__ import annotations

from app.simulation.types import (
    AgentPressure,
    AgentState,
    Opportunity,
    RelationshipState,
    WorldState,
)
from app.simulation.stages.agent_refresh import FOOD_CONSUMPTION

# ---------------------------------------------------------------------------
# Tunable constants
# ---------------------------------------------------------------------------

RESOURCE_BUFFER_TURNS = 5.0    # turns of food stock = "secure"
COIN_THRESHOLD = 10.0          # coin >= this → zero coin pressure
MEMORY_PRESSURE_SCALE = 0.25   # multiplier on summed negative memory weight
SICKNESS_PRESSURE_VALUE = 0.8  # fixed pressure when sick

# ---------------------------------------------------------------------------
# Component computations
# ---------------------------------------------------------------------------


def _hunger_component(agent: AgentState) -> tuple[float, str | None]:
    p = round(min(1.0, agent.hunger), 4)
    reason = f"hunger at {agent.hunger:.0%}" if p >= 0.3 else None
    return p, reason


def _resource_component(agent: AgentState) -> tuple[float, str | None]:
    daily = FOOD_CONSUMPTION.get(agent.profession.value, 1.0)
    turns = agent.inventory.food / max(daily, 0.001)
    food_p = max(0.0, 1.0 - turns / RESOURCE_BUFFER_TURNS)
    coin_p = max(0.0, 1.0 - agent.inventory.coin / COIN_THRESHOLD)
    p = round(min(1.0, 0.7 * food_p + 0.3 * coin_p), 4)
    parts: list[str] = []
    if food_p >= 0.5:
        parts.append(f"{agent.inventory.food:.1f} food ({turns:.1f} turns supply)")
    if coin_p >= 0.5:
        parts.append(f"{agent.inventory.coin:.1f} coin")
    reason = f"scarce: {', '.join(parts)}" if parts else None
    return p, reason


def _sickness_component(agent: AgentState) -> tuple[float, str | None]:
    if agent.is_sick:
        return SICKNESS_PRESSURE_VALUE, "is sick"
    return 0.0, None


def _social_component(
    agent: AgentState,
    relationships: list[RelationshipState],
) -> tuple[float, str | None]:
    incoming = [r for r in relationships if r.target_agent_id == agent.id]
    if not incoming:
        return 0.0, None
    avg_resentment = sum(r.resentment for r in incoming) / len(incoming)
    grudge_count = sum(1 for r in incoming if r.grudge_active)
    p = round(min(1.0, avg_resentment * 0.5 + grudge_count * 0.2), 4)
    if grudge_count:
        return p, f"{grudge_count} grudge(s) held against them"
    if avg_resentment >= 0.3:
        return p, f"community resentment {avg_resentment:.2f}"
    return p, None


def _memory_component(agent: AgentState) -> tuple[float, str | None]:
    negatives = [
        abs(m.emotional_weight)
        for m in agent.recent_memories
        if m.emotional_weight < -0.1
    ]
    if not negatives:
        return 0.0, None
    p = round(min(1.0, sum(negatives) * MEMORY_PRESSURE_SCALE), 4)
    reason = f"{len(negatives)} traumatic recent memory/memories" if p >= 0.15 else None
    return p, reason


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compute_agent_pressure(agent: AgentState, world: WorldState) -> AgentPressure:
    """
    Compute the full deterministic pressure profile for a single living agent.

    Pure function — same inputs always produce the same output.
    Called once per agent per turn by the compute_pressure pipeline stage.
    """
    hp, hr = _hunger_component(agent)
    rp, rr = _resource_component(agent)
    sp, sr = _sickness_component(agent)
    sop, sor = _social_component(agent, world.relationships)
    mp, mr = _memory_component(agent)

    total = round(hp + rp + sp + sop + mp, 4)

    # Sort reasons by their contributing pressure value, return top 3
    component_pairs = [(hp, hr), (rp, rr), (sp, sr), (sop, sor), (mp, mr)]
    top_reasons = [
        reason
        for _, reason in sorted(
            [(v, r) for v, r in component_pairs if r is not None],
            key=lambda x: -x[0],
        )[:3]
    ]

    return AgentPressure(
        agent_id=agent.id,
        hunger_pressure=hp,
        resource_pressure=rp,
        sickness_pressure=sp,
        social_pressure=sop,
        memory_pressure=mp,
        total=total,
        top_reasons=top_reasons,
    )


# ---------------------------------------------------------------------------
# Opportunity scoring
# ---------------------------------------------------------------------------

_FOOD_SEEKING = frozenset({"harvest_food", "buy_food"})
_HEALING = frozenset({"heal_self", "heal_agent"})
_PRODUCTION = frozenset({"harvest_food", "craft_tools", "trade_goods", "trade_food"})
_COOPERATIVE = frozenset({"heal_agent", "bless_village"})
_STRESS_RELEASE = frozenset({"gossip", "patrol"})


def score_opportunity(opp: Opportunity, pressure: AgentPressure | None) -> Opportunity:
    """
    Return a copy of the opportunity with a deterministic pressure-derived score.

    Baseline score is 1.0. Higher score = more attractive under current
    pressure conditions. This is consumed by action selection in resolve_actions.

    All modifiers are additive and visible — no hidden coefficients.
    """
    if pressure is None:
        return opp.model_copy(update={"score": 1.0})

    base = 1.0
    action = opp.action_type

    # Survival: very hungry → desperately seek food; rest becomes less appealing
    if pressure.hunger_pressure >= 0.6:
        if action in _FOOD_SEEKING:
            base += 1.5
        elif action == "rest":
            base -= 0.4

    # Resource scarcity: produce and trade aggressively
    if pressure.resource_pressure >= 0.5 and action in _PRODUCTION:
        base += 0.8

    # Sickness: healing rises above all else
    if pressure.sickness_pressure >= 0.5 and action in _HEALING:
        base += 2.0

    # Social pressure: less cooperative, more defensive
    if pressure.social_pressure >= 0.4:
        if action in _COOPERATIVE:
            base -= 0.3
        if action in _STRESS_RELEASE:
            base += 0.4

    # Low overall pressure: cooperative behaviour is more likely
    if pressure.total < 0.5 and action in _COOPERATIVE:
        base += 0.3

    # Surplus: when food is abundant (low resource pressure) selling is better
    # than harvesting more into an already-full stockpile.
    if pressure.resource_pressure < 0.2 and action == "trade_food":
        base += 0.7

    # Comfortable merchant: trade_goods becomes less urgent when the agent is
    # well-resourced overall — creates natural rest/variety turns.
    if pressure.resource_pressure < 0.2 and pressure.total < 0.5 and action == "trade_goods":
        base -= 0.3

    # High overall pressure: survival mode — gossip and patrol increase
    if pressure.total >= 2.5:
        if action == "gossip":
            base += 0.5
        if action == "patrol":
            base += 0.2
        # Desperate agents may steal
        if action == "steal_food":
            base += 1.0

    return opp.model_copy(update={"score": round(max(0.0, base), 4)})
