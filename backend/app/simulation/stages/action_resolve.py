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
from app.simulation.stages.agent_refresh import FOOD_CONSUMPTION as _FOOD_CONSUMPTION
from app.simulation.types import (
    AgentPressure,
    AgentState,
    InventorySnapshot,
    Opportunity,
    ResolvedAction,
    TurnContext,
    WorldState,
)

# Turns of food stock at which harvest yield starts to saturate.
# Mirrors RESOURCE_BUFFER_TURNS in pressure.py so the two systems agree.
_SURPLUS_TURNS = 5.0

# ---------------------------------------------------------------------------
# Deterministic flavor text — selected by (agent_id * prime + turn) % len
# ---------------------------------------------------------------------------

_BLESS_VARIANTS = [
    "led the morning prayer for the village",
    "gathered the villagers for a quiet blessing",
    "offered words of comfort to the weary",
    "performed a solemn rite of protection",
    "blessed the fields and hearths of the village",
]

_HARVEST_VARIANTS = [
    "harvested {food} food from the fields",
    "brought in {food} food from the crops",
    "gathered {food} food from the fields",
]

_STUDY_VARIANTS = [
    "studied the ancient scriptures",
    "read from the village chronicles",
    "penned notes on theology and village law",
    "copied sacred texts by candlelight",
]

_TEND_VARIANTS = [
    "tended the herb garden by the chapel",
    "pruned the chapel garden in quiet reflection",
    "gathered healing herbs from the chapel garden",
    "planted new rows in the chapel's small plot",
]

# When the best goal-matching opportunity scores below this threshold, the
# action selector falls through to the highest-scored opportunity overall
# (which may be rest). This allows a well-fed, low-pressure agent to take a
# break when their primary action has been repeatedly penalised, rather than
# grinding the same action at a tiny score for no narrative gain.
_GOAL_MIN_SCORE = 0.4


def _agent_name(world: WorldState | None, agent_id: int) -> str:
    """Resolve agent_id to display name; falls back to 'a villager' if not found."""
    if world is None:
        return f"agent {agent_id}"
    agent = world.agent_by_id(agent_id)
    return agent.name if agent else "a villager"

# Map goal.type → preferred action_types in priority order
_GOAL_ACTION_MAP: dict[str, list[str]] = {
    "produce":    ["harvest_food", "craft_tools", "trade_food"],
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
            best = max(candidates, key=lambda o: o.score)
            # If the best goal match has been actively scored but heavily
            # penalised (score > 0 but below threshold), let the agent fall
            # through to the overall best rather than grinding a near-zero
            # action every turn. Unscored opportunities (score == 0.0, as in
            # Phase 2 direct-call tests) always respect goal ordering.
            if best.score == 0.0 or best.score >= _GOAL_MIN_SCORE:
                return best

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
        # Saturation: large stockpile → diminishing returns (farmer is less
        # diligent when well-stocked, some produce left in the field).
        daily = _FOOD_CONSUMPTION.get(agent.profession.value, 1.0)
        stock_turns = agent.inventory.food / max(daily, 0.001)
        if stock_turns > _SURPLUS_TURNS:
            excess = min(1.0, (stock_turns - _SURPLUS_TURNS) / 20.0)
            saturation = round(1.0 - 0.2 * excess, 4)
        else:
            saturation = 1.0
        food_gained = round((yield_base + bonus) * saturation, 2)
        inv = inv.adjust(ResourceType.food, food_gained)
        turn = world.current_turn if world is not None else 0
        h_idx = (agent.id * 3 + turn) % len(_HARVEST_VARIANTS)
        harvest_outcome = _HARVEST_VARIANTS[h_idx].format(food=food_gained)
        return (
            ResolvedAction(
                agent_id=agent.id,
                action_type=action,
                outcome=harvest_outcome,
                details={"food_gained": food_gained},
            ),
            agent.model_copy(update={"inventory": inv}),
        )

    if action == "craft_tools":
        wood_cost = meta.get("wood_cost", 2.0)
        coin_gain = meta.get("coin_gain", 5.0)
        # Village pays in food for tools (barter economy — not all payment is coin)
        CRAFT_FOOD_BARTER = 0.5
        inv = inv.adjust(ResourceType.wood, -wood_cost)
        inv = inv.adjust(ResourceType.coin, coin_gain)
        inv = inv.adjust(ResourceType.food, CRAFT_FOOD_BARTER)
        return (
            ResolvedAction(
                agent_id=agent.id,
                action_type=action,
                outcome=f"crafted tools (+{coin_gain} coin, -{wood_cost} wood)",
                details={"coin_gained": coin_gain, "wood_spent": wood_cost, "food_gained": CRAFT_FOOD_BARTER},
            ),
            agent.model_copy(update={"inventory": inv}),
        )

    if action == "trade_goods":
        base = meta.get("coin_gain_base", 3.0)
        # demand_factor captures current village food scarcity: scarce → premium,
        # abundant → softer market. Set in opportunity_gen; defaults to 1.0 for
        # backwards-compatible calls (tests, Phase 2 pipeline).
        demand_factor = meta.get("demand_factor", 1.0)
        # Cunning multiplies trading profit
        cunning_mult = 1.0 + agent.personality_traits.get("cunning", 0.5)
        # State modifier: coin-poor merchant trades harder; coin-rich is complacent.
        coin_stock = agent.inventory.coin
        if coin_stock < 5.0:
            state_mult = 1.15   # motivated — needs money
        elif coin_stock > 25.0:
            state_mult = 0.90   # complacent — already well-off
        else:
            state_mult = 1.0
        # Personal comfort modifier: food security affects trading focus.
        # Well-fed trader concentrates fully; a hungry one is distracted.
        # Calibrated so that food=9 (food=10 minus one turn of consumption for
        # a merchant) yields exactly 1.0, keeping existing numeric test
        # assertions correct (refresh_agents runs before action resolution).
        food_stock = agent.inventory.food
        if food_stock >= 13.0:
            personal_mult = 1.05
        elif food_stock < 5.0:
            personal_mult = 0.95
        else:
            # Linear interpolation: food=5→0.95, food=9→1.0, food=13→1.05
            personal_mult = round(0.95 + (food_stock - 5.0) / 8.0 * 0.10, 3)
        coin_gain = round(base * cunning_mult * state_mult * demand_factor * personal_mult, 2)
        # Merchants also receive some food in trade (barter component of commerce)
        TRADE_FOOD_BARTER = 1.0
        inv = inv.adjust(ResourceType.coin, coin_gain)
        inv = inv.adjust(ResourceType.food, TRADE_FOOD_BARTER)
        # Outcome text varies by market conditions for chronicle readability.
        if demand_factor >= 1.15:
            outcome_text = f"traded goods at a premium for {coin_gain} coin"
        elif demand_factor <= 1.0 and personal_mult <= 0.97:
            outcome_text = f"traded goods for {coin_gain} coin, margins feeling thin"
        elif state_mult >= 1.15:
            outcome_text = f"traded hard, earning {coin_gain} coin"
        else:
            outcome_text = f"traded goods for {coin_gain} coin"
        return (
            ResolvedAction(
                agent_id=agent.id,
                action_type=action,
                outcome=outcome_text,
                details={"coin_gained": coin_gain, "food_gained": TRADE_FOOD_BARTER},
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
        # Healer earns a coin stipend and a small food payment per treatment.
        # Village compensates healers in both coin and food (barter economy).
        HEALER_STIPEND = 2.0
        HEALER_FOOD = 0.5
        inv = inv.adjust(ResourceType.medicine, -medicine_cost)
        inv = inv.adjust(ResourceType.coin, HEALER_STIPEND)
        inv = inv.adjust(ResourceType.food, HEALER_FOOD)
        return (
            ResolvedAction(
                agent_id=agent.id,
                action_type=action,
                outcome=f"healed {_agent_name(world, target_id)}",
                details={
                    "medicine_spent": medicine_cost,
                    "coin_earned": HEALER_STIPEND,
                    "food_gained": HEALER_FOOD,
                    "healed_agent_id": target_id,
                },
            ),
            agent.model_copy(update={"inventory": inv}),
        )

    if action == "pray":
        # Shrine donations provide modest food and coin
        PRAY_FOOD = 0.3
        PRAY_COIN = 0.5
        new_inv = inv.adjust(ResourceType.food, PRAY_FOOD)
        new_inv = new_inv.adjust(ResourceType.coin, PRAY_COIN)
        return (
            ResolvedAction(
                agent_id=agent.id, action_type=action,
                outcome="prayed at the shrine",
                details={"food_gained": PRAY_FOOD, "coin_gained": PRAY_COIN},
            ),
            agent.model_copy(update={"inventory": new_inv}),
        )

    if action == "bless_village":
        turn = world.current_turn if world is not None else 0
        idx = (agent.id * 7 + turn) % len(_BLESS_VARIANTS)
        # Villagers offer food and coin in gratitude for blessings (tithe + alms)
        BLESS_FOOD = 0.5
        BLESS_COIN = 1.0
        new_inv = inv.adjust(ResourceType.food, BLESS_FOOD)
        new_inv = new_inv.adjust(ResourceType.coin, BLESS_COIN)
        return (
            ResolvedAction(
                agent_id=agent.id, action_type=action,
                outcome=_BLESS_VARIANTS[idx],
                details={"food_gained": BLESS_FOOD, "coin_gained": BLESS_COIN},
            ),
            agent.model_copy(update={"inventory": new_inv}),
        )

    if action == "study":
        turn = world.current_turn if world is not None else 0
        idx = (agent.id * 5 + turn) % len(_STUDY_VARIANTS)
        # Shrine receives small donations during quiet religious days
        STUDY_FOOD = 0.3
        STUDY_COIN = 0.5
        new_inv = inv.adjust(ResourceType.food, STUDY_FOOD)
        new_inv = new_inv.adjust(ResourceType.coin, STUDY_COIN)
        return (
            ResolvedAction(
                agent_id=agent.id, action_type=action,
                outcome=_STUDY_VARIANTS[idx],
                details={"food_gained": STUDY_FOOD, "coin_gained": STUDY_COIN},
            ),
            agent.model_copy(update={"inventory": new_inv}),
        )

    if action == "tend_garden":
        turn = world.current_turn if world is not None else 0
        idx = (agent.id * 11 + turn) % len(_TEND_VARIANTS)
        # Chapel garden produces food; villagers leave small offerings
        GARDEN_FOOD = 0.3
        GARDEN_COIN = 0.5
        new_inv = inv.adjust(ResourceType.food, GARDEN_FOOD)
        new_inv = new_inv.adjust(ResourceType.coin, GARDEN_COIN)
        return (
            ResolvedAction(
                agent_id=agent.id, action_type=action,
                outcome=_TEND_VARIANTS[idx],
                details={"food_gained": GARDEN_FOOD, "coin_gained": GARDEN_COIN},
            ),
            agent.model_copy(update={"inventory": new_inv}),
        )

    if action == "patrol":
        # Soldier receives food rations and coin wages for service
        PATROL_FOOD = 0.5
        PATROL_COIN = 1.5
        new_inv = inv.adjust(ResourceType.food, PATROL_FOOD)
        new_inv = new_inv.adjust(ResourceType.coin, PATROL_COIN)
        return (
            ResolvedAction(
                agent_id=agent.id, action_type=action,
                outcome="patrolled the village perimeter",
                details={"food_gained": PATROL_FOOD, "coin_gained": PATROL_COIN},
            ),
            agent.model_copy(update={"inventory": new_inv}),
        )

    # rest (default fallback) — passive subsistence income from daily life
    REST_COIN = 0.5   # casual labour, errands, minor tasks
    new_inv = inv.adjust(ResourceType.coin, REST_COIN)
    return (
        ResolvedAction(
            agent_id=agent.id, action_type="rest",
            outcome="rested", details={"coin_gained": REST_COIN},
        ),
        agent.model_copy(update={"inventory": new_inv}),
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

        # Track occupational fatigue for farmer and blacksmith.
        # Consecutive work turns increment; any rest (or non-work action) resets.
        if agent.profession.value in ("farmer", "blacksmith"):
            _WORK_ACTIONS = {"harvest_food", "craft_tools"}
            if action_record.action_type in _WORK_ACTIONS:
                new_cwt = updated_agent.consecutive_work_turns + 1
            else:
                new_cwt = 0
            updated_agent = updated_agent.model_copy(update={"consecutive_work_turns": new_cwt})

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
