"""
Stage 2 — Agent Refresh

Deterministic per-agent state updates applied at the top of every turn,
before opportunity generation.

Rules (simple, easy to tune):
- Each profession has a daily food consumption rate.
- If enough food is available, hunger decreases by 0.2 (eating well).
- Partial food: hunger increases proportionally to the shortfall.
- No food at all: hunger increases by HUNGER_INCREASE_PER_TURN.
- Sick agents consume more food (SICKNESS_HUNGER_MULTIPLIER).
- hunger >= 1.0 → agent dies (is_alive = False).

Extension point:
- Health engine will add sickness-spread logic after this stage.
- Season modifier (e.g. winter increases consumption) hooks in here.
"""
from app.enums import ResourceType
from app.simulation.types import AgentState, TurnContext

HUNGER_INCREASE_PER_TURN = 0.15
SICKNESS_HUNGER_MULTIPLIER = 1.3

# Daily food consumption by profession (units per turn)
_FOOD_CONSUMPTION: dict[str, float] = {
    "farmer": 0.8,
    "blacksmith": 1.2,
    "merchant": 1.0,
    "healer": 0.9,
    "priest": 0.7,
    "soldier": 1.3,
}


def refresh_agent(agent: AgentState) -> AgentState:
    if not agent.is_alive:
        return agent

    consumption = _FOOD_CONSUMPTION.get(agent.profession.value, 1.0)
    if agent.is_sick:
        consumption *= SICKNESS_HUNGER_MULTIPLIER

    food_available = agent.inventory.food

    if food_available >= consumption:
        new_inventory = agent.inventory.adjust(ResourceType.food, -consumption)
        new_hunger = max(0.0, round(agent.hunger - 0.2, 4))
    else:
        # Consume what is available; raise hunger proportional to shortfall
        new_inventory = agent.inventory.adjust(ResourceType.food, -food_available)
        shortfall_ratio = 1.0 - food_available / max(consumption, 0.001)
        hunger_increase = round(HUNGER_INCREASE_PER_TURN * shortfall_ratio, 4)
        new_hunger = min(1.0, round(agent.hunger + hunger_increase, 4))

    is_alive = new_hunger < 1.0

    return agent.model_copy(update={
        "hunger": new_hunger,
        "is_alive": is_alive,
        "inventory": new_inventory,
    })


def refresh_agents(ctx: TurnContext) -> TurnContext:
    updated_agents = [refresh_agent(a) for a in ctx.world_state.agents]
    updated_world = ctx.world_state.model_copy(update={"agents": updated_agents})
    return ctx.model_copy(update={"world_state": updated_world})
