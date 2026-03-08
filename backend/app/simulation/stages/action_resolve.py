"""
Stage 4 — Action Resolution

For each living agent: select best opportunity → apply deterministic effects
→ produce a ResolvedAction and update agent state.

Selection logic:
- Iterate agent.goals sorted by priority.
- Match the goal type to a preferred action list.
- Pick the first matching opportunity.
- Fall back to the first non-rest opportunity, then rest.

Extension point (Phase 6+):
- LLM-driven selection: replace _select_action() with an async call that
  receives the agent's context and returns a chosen action_type.
  The resolution logic (_resolve) stays deterministic.
"""
from __future__ import annotations

from app.enums import ResourceType
from app.simulation.types import (
    AgentState,
    InventorySnapshot,
    Opportunity,
    ResolvedAction,
    TurnContext,
    WorldState,
)

# Map goal.type → preferred action_types in priority order
_GOAL_ACTION_MAP: dict[str, list[str]] = {
    "produce":    ["harvest_food", "craft_tools"],
    "heal":       ["heal_agent", "heal_self"],
    "trade":      ["trade_goods"],
    "protect":    ["patrol"],
    "maintain":   ["bless_village"],
    "tend":       ["pray"],
    "accumulate": ["craft_tools", "trade_goods"],
    "earn":       ["patrol", "trade_goods"],
    "stockpile":  ["harvest_food"],
}


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------


def _select_action(agent: AgentState, opps: list[Opportunity]) -> Opportunity:
    """
    Choose the best available opportunity for this agent.

    Selection algorithm:
    1. Filter opportunities to those belonging to this agent.
    2. Iterate goals sorted by (priority ASC, original_list_index ASC).
       Tie-break rule: when two goals share the same priority value, the one
       appearing earlier in the agent's goals list wins. This is made explicit
       via the secondary sort key rather than relying on Python's stable-sort
       side effect.
    3. For each goal, try every preferred action type in order; pick the first
       matching opportunity.
    4. Fallback: first non-rest opportunity, then rest.

    Extension point: replace with LLM call in Phase 6.
    """
    agent_opps = [o for o in opps if o.agent_id == agent.id]
    if not agent_opps:
        return Opportunity(agent_id=agent.id, action_type="rest")

    # Explicit tie-break: (priority, original index) — never depends on sort stability alone.
    sorted_goals = [
        g for _, g in sorted(
            enumerate(agent.goals),
            key=lambda ig: (ig[1].get("priority", 99), ig[0]),
        )
    ]

    for goal in sorted_goals:
        preferred = _GOAL_ACTION_MAP.get(goal.get("type", ""), [])
        for action_type in preferred:
            match = next((o for o in agent_opps if o.action_type == action_type), None)
            if match:
                return match

    # Fallback: first non-rest opportunity, or rest
    non_rest = [o for o in agent_opps if o.action_type != "rest"]
    return non_rest[0] if non_rest else agent_opps[0]


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


def _resolve(
    opp: Opportunity,
    agent: AgentState,
) -> tuple[ResolvedAction, AgentState]:
    """Apply action effects; return (action_record, updated_agent)."""
    inv = agent.inventory
    action = opp.action_type
    meta = opp.metadata

    if action == "harvest_food":
        yield_base = meta.get("yield_base", 3.0)
        # Warmth personality boosts yield slightly (calm, patient farming)
        bonus = round(agent.personality_traits.get("warmth", 0.5) * 0.5, 2)
        food_gained = round(yield_base + bonus, 2)
        inv = inv.adjust(ResourceType.food, food_gained)
        return (
            ResolvedAction(
                agent_id=agent.id,
                action_type=action,
                outcome=f"harvested {food_gained} food",
                details={"food_gained": food_gained},
            ),
            agent.model_copy(update={"inventory": inv}),
        )

    if action == "craft_tools":
        wood_cost = meta.get("wood_cost", 2.0)
        coin_gain = meta.get("coin_gain", 5.0)
        inv = inv.adjust(ResourceType.wood, -wood_cost)
        inv = inv.adjust(ResourceType.coin, coin_gain)
        return (
            ResolvedAction(
                agent_id=agent.id,
                action_type=action,
                outcome=f"crafted tools (+{coin_gain} coin, -{wood_cost} wood)",
                details={"coin_gained": coin_gain, "wood_spent": wood_cost},
            ),
            agent.model_copy(update={"inventory": inv}),
        )

    if action == "trade_goods":
        base = meta.get("coin_gain_base", 3.0)
        # Cunning multiplies trading profit
        coin_gain = round(base * (1.0 + agent.personality_traits.get("cunning", 0.5)), 2)
        inv = inv.adjust(ResourceType.coin, coin_gain)
        return (
            ResolvedAction(
                agent_id=agent.id,
                action_type=action,
                outcome=f"traded goods for {coin_gain} coin",
                details={"coin_gained": coin_gain},
            ),
            agent.model_copy(update={"inventory": inv}),
        )

    if action == "heal_self":
        medicine_cost = meta.get("medicine_cost", 1.0)
        inv = inv.adjust(ResourceType.medicine, -medicine_cost)
        return (
            ResolvedAction(
                agent_id=agent.id,
                action_type=action,
                outcome="healed self",
                details={"medicine_spent": medicine_cost},
            ),
            agent.model_copy(update={"inventory": inv, "is_sick": False}),
        )

    if action == "heal_agent":
        medicine_cost = meta.get("medicine_cost", 1.0)
        target_id = opp.target_agent_id
        inv = inv.adjust(ResourceType.medicine, -medicine_cost)
        return (
            ResolvedAction(
                agent_id=agent.id,
                action_type=action,
                outcome=f"healed agent {target_id}",
                details={"medicine_spent": medicine_cost, "healed_agent_id": target_id},
            ),
            agent.model_copy(update={"inventory": inv}),
        )

    if action == "pray":
        return (
            ResolvedAction(
                agent_id=agent.id,
                action_type=action,
                outcome="prayed at the shrine",
                details={},
            ),
            agent,
        )

    if action == "bless_village":
        return (
            ResolvedAction(
                agent_id=agent.id,
                action_type=action,
                outcome="blessed the village",
                details={},
            ),
            agent,
        )

    if action == "patrol":
        return (
            ResolvedAction(
                agent_id=agent.id,
                action_type=action,
                outcome="patrolled the village perimeter",
                details={},
            ),
            agent,
        )

    # rest (default fallback)
    return (
        ResolvedAction(
            agent_id=agent.id,
            action_type="rest",
            outcome="rested",
            details={},
        ),
        agent,
    )


# ---------------------------------------------------------------------------
# Stage entry point
# ---------------------------------------------------------------------------


def resolve_actions(ctx: TurnContext) -> TurnContext:
    """
    Resolve every living agent's action for this turn.

    heal_agent side-effect: the target agent is marked not-sick after
    all resolutions are collected, so order of healing doesn't matter.
    """
    resolved: list[ResolvedAction] = []
    agent_map: dict[int, AgentState] = {a.id: a for a in ctx.world_state.agents}

    for agent in ctx.world_state.living_agents:
        opp = _select_action(agent, ctx.opportunities)
        action_record, updated_agent = _resolve(opp, agent)
        resolved.append(action_record)
        agent_map[agent.id] = updated_agent

    # Apply heal_agent side-effects
    for action in resolved:
        if action.action_type == "heal_agent" and action.succeeded:
            target_id = action.details.get("healed_agent_id")
            if target_id and target_id in agent_map:
                agent_map[target_id] = agent_map[target_id].model_copy(
                    update={"is_sick": False}
                )

    updated_agents = [agent_map[a.id] for a in ctx.world_state.agents]
    updated_world = ctx.world_state.model_copy(update={"agents": updated_agents})

    return ctx.model_copy(update={
        "resolved_actions": resolved,
        "world_state": updated_world,
    })
