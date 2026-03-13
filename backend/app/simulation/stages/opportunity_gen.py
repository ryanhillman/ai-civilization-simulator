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

Phase 6 changes (state feedback)
---------------------------------
- Harvest yield varies by season: summer peaks, winter dips.
- trade_goods coin base varies by season: winter demand is highest.
- bless_village is only offered when the village has genuine need
  (any agent hungry > 0.15 or sick); otherwise the priest prays.
- patrol is only offered when there is an active theft threat or it is
  a scheduled patrol turn (turn % 3 == 0); soldiers rest otherwise.
  This prevents both actions from firing identically every single day.

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
    WorldState,
)

# ---------------------------------------------------------------------------
# Seasonal yield tables
# ---------------------------------------------------------------------------

# Base food gained per harvest turn (before personality + event modifiers).
# Summer peaks, winter is sparse, spring/autumn are moderate.
# Yields are calibrated for a 6-agent village: Aldric (farmer) must produce
# enough surplus (~5 food/turn) to feed 5 non-farming neighbours via trade.
_HARVEST_YIELD_BY_SEASON: dict[str, float] = {
    "spring": 6.0,
    "summer": 7.0,
    "autumn": 5.0,
    "winter": 3.0,
}

# Base coin gained per trade_goods turn.
# Demand rises in winter (scarcity premium), falls in summer (abundance).
_TRADE_COIN_BASE_BY_SEASON: dict[str, float] = {
    "spring": 3.0,
    "summer": 2.5,
    "autumn": 3.5,
    "winter": 4.0,
}

# Base coin gained per craft_tools turn.
# Winter demand highest (indoor work, maintenance), summer lowest (field season).
_CRAFT_COIN_BY_SEASON: dict[str, float] = {
    "spring": 4.5,
    "summer": 4.0,
    "autumn": 5.0,
    "winter": 6.0,
}

# ---------------------------------------------------------------------------
# Repetition damping
# ---------------------------------------------------------------------------

# Actions whose EventType memories are stored (emotional_weight >= 0.15):
#   harvest → EventType.harvest (0.2), theft → EventType.theft (0.7),
#   trade_goods / craft_tools → EventType.trade (0.15, raised from 0.1)
_ACTION_MEMORY_EVENT: dict[str, str] = {
    "harvest_food": "harvest",
    "steal_food":   "theft",
    "trade_goods":  "trade",   # merchant repetition tracking
    "craft_tools":  "trade",   # blacksmith repetition tracking
}

# How many recent turns to look back per event type.
# harvest/theft use an unlimited window (original behaviour).
# trade uses a short sliding window so the penalty decays naturally after a rest.
_REPETITION_WINDOW: dict[str, int] = {
    "harvest": 9999,
    "theft":   9999,
    "trade":   3,     # only the last 3 turns count for trade/craft repetition
    # A 3-turn window decays the penalty quickly after a rest day, producing a
    # natural 2-trade / 2-rest rhythm rather than 4+ consecutive rest turns.
}

_REPEAT_PENALTY = 0.25   # score reduction per repeated memory (capped at 3 repeats)


def _repetition_score_penalty(
    action_type: str, recent_memories: list, current_turn: int = 0
) -> float:
    """
    Return a score reduction for actions the agent has repeatedly taken recently.

    harvest/theft look at all-time memory; trade/craft use a 5-turn sliding
    window so the penalty decays naturally after a turn of inactivity.
    """
    event_str = _ACTION_MEMORY_EVENT.get(action_type)
    if not event_str or not recent_memories:
        return 0.0
    window = _REPETITION_WINDOW.get(event_str, 9999)
    cutoff = current_turn - window
    count = sum(
        1 for m in recent_memories
        if m.event_type.value == event_str and m.turn_number >= cutoff
    )
    return _REPEAT_PENALTY * min(count, 3)

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


def _village_demand_factor(all_agents: list[AgentState]) -> float:
    """
    Village-level trade demand proxy derived from average agent hunger.

    Hunger is a time-integrated signal: it accumulates across turns when
    food runs short (illness, poor harvest, winter) and declines when
    supply recovers. High village hunger signals genuine scarcity — people
    pay more for goods when desperate.

    Baseline (hunger=0): factor=1.0.  Peak (everyone fully hungry): factor=1.2.
    Range: [1.0, 1.2] — no discount when the village is well-fed.
    """
    if not all_agents:
        return 1.0
    avg_hunger = sum(a.hunger for a in all_agents) / len(all_agents)
    factor = 1.0 + avg_hunger * 0.2
    return round(min(1.2, max(1.0, factor)), 3)


# ---------------------------------------------------------------------------
# Per-profession opportunity builders
# ---------------------------------------------------------------------------


def _profession_opportunities(
    agent: AgentState,
    all_agents: list[AgentState],
    world_events: list[WorldEventRecord],
    world_state: WorldState,
) -> list[Opportunity]:
    aid = agent.id
    opps: list[Opportunity] = []

    # Universal: every agent can rest
    opps.append(Opportunity(agent_id=aid, action_type="rest"))

    profession = agent.profession
    harvest_mult = _harvest_multiplier(world_events)
    season_name = world_state.current_season.value

    if profession == Profession.farmer:
        season_yield = _HARVEST_YIELD_BY_SEASON.get(season_name, 3.0)
        opps.append(Opportunity(
            agent_id=aid,
            action_type="harvest_food",
            metadata={"yield_base": round(season_yield * harvest_mult, 4)},
        ))

    elif profession == Profession.blacksmith:
        if agent.inventory.wood >= 2.0:
            season_coin = _CRAFT_COIN_BY_SEASON.get(season_name, 5.0)
            opps.append(Opportunity(
                agent_id=aid,
                action_type="craft_tools",
                metadata={"wood_cost": 2.0, "coin_gain": season_coin},
            ))
        else:
            # No wood available — sell expertise and labour instead (less efficient).
            # demand_factor reflects village food state so fallback output varies.
            season_base = _TRADE_COIN_BASE_BY_SEASON.get(season_name, 3.0)
            opps.append(Opportunity(
                agent_id=aid,
                action_type="trade_goods",
                metadata={
                    "coin_gain_base": round(season_base * 0.7, 2),
                    "demand_factor": _village_demand_factor(all_agents),
                },
            ))

    elif profession == Profession.merchant:
        season_base = _TRADE_COIN_BASE_BY_SEASON.get(season_name, 3.0)
        opps.append(Opportunity(
            agent_id=aid,
            action_type="trade_goods",
            metadata={"coin_gain_base": season_base, "demand_factor": _village_demand_factor(all_agents)},
        ))

    elif profession == Profession.healer:
        if agent.is_sick and agent.inventory.medicine >= 1.0:
            opps.append(Opportunity(
                agent_id=aid,
                action_type="heal_self",
                metadata={"medicine_cost": 1.0},
            ))
        # Self-preservation: a healer who is themselves at serious risk of
        # starvation (hunger > 0.4) will not spend their remaining energy
        # treating others. They must first secure their own survival.
        _HEALER_SELF_PRESERVATION_THRESHOLD = 0.4
        if agent.hunger <= _HEALER_SELF_PRESERVATION_THRESHOLD:
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
        # bless_village only when the village has genuine need — otherwise
        # the priest would bless every single day with no meaningful effect
        village_in_need = any(
            a.hunger > 0.15 or a.is_sick
            for a in all_agents
        )
        if village_in_need:
            opps.append(Opportunity(agent_id=aid, action_type="bless_village"))
        # Rotate between quiet activities on a 3-turn cycle so the chronicle
        # shows "studying", "tending the garden", and "praying" rather than
        # an identical silent pray entry every non-blessing day.
        _QUIET_PRIEST = ["pray", "study", "tend_garden"]
        quiet_action = _QUIET_PRIEST[world_state.current_turn % 3]
        opps.append(Opportunity(agent_id=aid, action_type=quiet_action))

    elif profession == Profession.soldier:
        if not _patrol_blocked(world_events):
            # Patrol when there is an active theft threat OR on a scheduled
            # patrol turn (every 3 turns).  Prevents daily identical entries.
            has_threat = any(
                r.rumor_type == "theft"
                for r in world_state.active_rumors
            )
            if has_threat or world_state.current_turn % 3 == 0:
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
    current_turn = ctx.world_state.current_turn
    opps: list[Opportunity] = []

    for agent in all_agents:
        pressure = ctx.pressures.get(agent.id)
        raw_opps = _profession_opportunities(agent, all_agents, ctx.world_events, ctx.world_state)

        # Add steal opportunity for desperate agents
        steal = _steal_food_opportunity(agent, all_agents, pressure) if pressure else None
        if steal:
            raw_opps.append(steal)

        scored_opps = []
        for o in raw_opps:
            scored = score_opportunity(o, pressure)
            penalty = _repetition_score_penalty(o.action_type, agent.recent_memories, current_turn)
            if penalty > 0.0:
                scored = scored.model_copy(
                    update={"score": round(max(0.1, scored.score - penalty), 4)}
                )
            scored_opps.append(scored)
        opps.extend(scored_opps)

    return ctx.model_copy(update={"opportunities": opps})
