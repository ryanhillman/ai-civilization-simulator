"""
Stage 4 — Action Resolution

For each living agent: select best opportunity → apply deterministic effects
→ produce a ResolvedAction and update agent state.

Selection logic (Phase 3)
--------------------------
Normal mode (total pressure < 2.5):
  1. Iterate goals sorted by (priority ASC, original_index ASC).
  2. For each goal, pick the highest-scored matching opportunity.
  3. Fallback: highest-scored non-rest opportunity, then rest.

Survival mode (total pressure >= 2.5):
  Score becomes the primary selector — the agent acts on whatever the
  pressure system rates most urgent, overriding stated goals. This produces
  emergent desperate behaviour (stealing, aggressive trading) when multiple
  pressure domains are simultaneously elevated.

Multi-agent side effects
------------------------
heal_agent   → target marked not-sick after all actions resolved
trade_food   → buyer inventory updated (food ↑, coin ↓) after all resolved
steal_food   → victim inventory updated (food ↓) after all resolved

Extension point (Phase 6+)
---------------------------
Replace _select_action() with an async LLM call that receives the agent's
scored opportunity list and pressure profile, then returns a chosen action.
The resolution logic (_resolve) stays deterministic regardless.
"""
from __future__ import annotations

from app.enums import ResourceType
from app.simulation.types import (
    AgentPressure,
    AgentState,
    InventorySnapshot,
    Opportunity,
    ResolvedAction,
    TurnContext,
    WorldState,
)


def _agent_name(world: WorldState | None, agent_id: int) -> str:
    """Resolve agent_id to display name; falls back to 'a villager' if not found."""
    if world is None:
        return f"agent {agent_id}"
    agent = world.agent_by_id(agent_id)
    return agent.name if agent else "a villager"

# Map goal.type → preferred action_types in priority order
_GOAL_ACTION_MAP: dict[str, list[str]] = {
    "produce":    ["harvest_food", "craft_tools"],
    "heal":       ["heal_agent", "heal_self"],
    "trade":      ["trade_goods", "trade_food"],
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


def _select_action(
    agent: AgentState,
    opps: list[Opportunity],
    pressure: AgentPressure | None = None,
) -> Opportunity:
    """
    Choose the best available opportunity for this agent.

    Signature accepts an optional pressure argument so Phase 2 callers
    (existing tests) work unchanged while Phase 3 passes pressure.

    Survival mode: when total pressure >= 2.5, score is the primary
    selector — stated goals are overridden by urgency.

    Normal mode:
      1. Filter to this agent's opportunities.
      2. Iterate goals sorted by (priority ASC, original_index ASC).
         Tie-break rule: earlier in goals list wins (explicit sort key,
         not relying on Python stable-sort side effect).
      3. For each goal, pick the highest-scored matching opportunity.
      4. Fallback: highest-scored non-rest, then rest.
    """
    agent_opps = [o for o in opps if o.agent_id == agent.id]
    if not agent_opps:
        return Opportunity(agent_id=agent.id, action_type="rest", score=0.0)

    # Survival mode: pressure overrides goals
    if pressure is not None and pressure.total >= 2.5:
        return max(agent_opps, key=lambda o: o.score)

    # Normal mode: goal-driven selection with score as tie-breaker
    sorted_goals = [
        g for _, g in sorted(
            enumerate(agent.goals),
            key=lambda ig: (ig[1].get("priority", 99), ig[0]),
        )
    ]

    for goal in sorted_goals:
        preferred = _GOAL_ACTION_MAP.get(goal.get("type", ""), [])
        candidates = [o for o in agent_opps if o.action_type in preferred]
        if candidates:
            return max(candidates, key=lambda o: o.score)

    # Fallback: highest-scored non-rest, or rest
    non_rest = [o for o in agent_opps if o.action_type != "rest"]
    if non_rest:
        return max(non_rest, key=lambda o: o.score)
    return agent_opps[0]


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


def _resolve(
    opp: Opportunity,
    agent: AgentState,
    world: WorldState | None = None,
) -> tuple[ResolvedAction, AgentState]:
    """Apply action effects; return (action_record, updated_agent)."""
    inv = agent.inventory
    action = opp.action_type
    meta = opp.metadata

    if action == "harvest_food":
        yield_base = meta.get("yield_base", 3.0)
        # Warmth personality boosts yield (calm, patient farming)
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

    if action == "trade_food":
        # Seller transfers food and receives coin.
        # Buyer inventory is updated as a side-effect in resolve_actions().
        food_amount = meta.get("food_amount", 2.0)
        price = meta.get("price", 1.5)
        buyer_id = meta.get("buyer_id") or opp.target_agent_id
        inv = inv.adjust(ResourceType.food, -food_amount)
        inv = inv.adjust(ResourceType.coin, price)
        return (
            ResolvedAction(
                agent_id=agent.id,
                action_type=action,
                outcome=f"sold {food_amount} food to {_agent_name(world, buyer_id)} for {price} coin",
                details={
                    "food_sold": food_amount,
                    "coin_received": price,
                    "buyer_id": buyer_id,
                },
            ),
            agent.model_copy(update={"inventory": inv}),
        )

    if action == "steal_food":
        steal_amount = meta.get("steal_amount", 2.0)
        target_id = meta.get("target_id") or opp.target_agent_id
        inv = inv.adjust(ResourceType.food, steal_amount)
        return (
            ResolvedAction(
                agent_id=agent.id,
                action_type=action,
                outcome=f"stole {steal_amount} food from {_agent_name(world, target_id)}",
                details={
                    "food_stolen": steal_amount,
                    "victim_id": target_id,
                },
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
                outcome=f"healed {_agent_name(world, target_id)}",
                details={"medicine_spent": medicine_cost, "healed_agent_id": target_id},
            ),
            agent.model_copy(update={"inventory": inv}),
        )

    if action == "pray":
        return (
            ResolvedAction(
                agent_id=agent.id, action_type=action,
                outcome="prayed at the shrine", details={},
            ),
            agent,
        )

    if action == "bless_village":
        return (
            ResolvedAction(
                agent_id=agent.id, action_type=action,
                outcome="blessed the village", details={},
            ),
            agent,
        )

    if action == "patrol":
        return (
            ResolvedAction(
                agent_id=agent.id, action_type=action,
                outcome="patrolled the village perimeter", details={},
            ),
            agent,
        )

    # rest (default fallback)
    return (
        ResolvedAction(
            agent_id=agent.id, action_type="rest",
            outcome="rested", details={},
        ),
        agent,
    )


# ---------------------------------------------------------------------------
# Stage entry point
# ---------------------------------------------------------------------------


def resolve_actions(ctx: TurnContext) -> TurnContext:
    """
    Resolve every living agent's action for this turn.

    Multi-agent side effects applied after all primary resolutions:
      heal_agent  → target marked not-sick
      trade_food  → buyer gains food, loses coin
      steal_food  → victim loses food; creates resentment (handled by
                    update_relationships in the Phase 3 pipeline)
    """
    resolved: list[ResolvedAction] = []
    agent_map: dict[int, AgentState] = {a.id: a for a in ctx.world_state.agents}

    for agent in ctx.world_state.living_agents:
        pressure = ctx.pressures.get(agent.id)

        # Phase 5: AI decision support hint — use pre-selected action only
        # if it matches an actual opportunity in the candidate list (validation).
        # Falls back to deterministic selection if hint is absent or invalid.
        pre_type = ctx.pre_selected_actions.get(agent.id)
        if pre_type:
            agent_opps = [o for o in ctx.opportunities if o.agent_id == agent.id]
            hint_opp = next((o for o in agent_opps if o.action_type == pre_type), None)
            opp = hint_opp if hint_opp is not None else _select_action(agent, ctx.opportunities, pressure)
        else:
            opp = _select_action(agent, ctx.opportunities, pressure)

        action_record, updated_agent = _resolve(opp, agent, ctx.world_state)
        resolved.append(action_record)
        agent_map[agent.id] = updated_agent

    # --- Side effects ---

    for action in resolved:
        # heal_agent: mark target not-sick
        if action.action_type == "heal_agent" and action.succeeded:
            target_id = action.details.get("healed_agent_id")
            if target_id and target_id in agent_map:
                agent_map[target_id] = agent_map[target_id].model_copy(
                    update={"is_sick": False}
                )

        # trade_food: buyer receives food, pays coin
        elif action.action_type == "trade_food" and action.succeeded:
            buyer_id = action.details.get("buyer_id")
            food = action.details.get("food_sold", 0.0)
            price = action.details.get("coin_received", 0.0)
            if buyer_id and buyer_id in agent_map:
                buyer = agent_map[buyer_id]
                new_inv = buyer.inventory.adjust(ResourceType.food, food)
                new_inv = new_inv.adjust(ResourceType.coin, -price)
                agent_map[buyer_id] = buyer.model_copy(update={"inventory": new_inv})

        # steal_food: victim loses food
        elif action.action_type == "steal_food" and action.succeeded:
            victim_id = action.details.get("victim_id")
            stolen = action.details.get("food_stolen", 0.0)
            if victim_id and victim_id in agent_map:
                victim = agent_map[victim_id]
                new_inv = victim.inventory.adjust(ResourceType.food, -stolen)
                agent_map[victim_id] = victim.model_copy(update={"inventory": new_inv})

    updated_agents = [agent_map[a.id] for a in ctx.world_state.agents]
    updated_world = ctx.world_state.model_copy(update={"agents": updated_agents})

    return ctx.model_copy(update={
        "resolved_actions": resolved,
        "world_state": updated_world,
    })
