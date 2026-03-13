"""
Stage 2 — Agent Refresh

Deterministic per-agent state updates applied at the top of every turn,
before opportunity generation.

Rules (simple, easy to tune):
- Each profession has a daily food consumption rate.
- If enough food is available, hunger decreases by 0.2 (eating well).
- Partial food: hunger increases proportionally to the shortfall.
- No food at all: hunger increases by HUNGER_INCREASE_PER_TURN.
- Sick agents consume slightly more food (SICKNESS_HUNGER_MULTIPLIER).
- Spontaneous recovery: (agent.id * 7 + turn) % SICKNESS_RECOVERY_PERIOD == 0
  causes a sick agent to recover at the END of the turn (after consumption),
  giving ~8 turns average illness duration without healer intervention.
- hunger >= 1.0 → agent dies (is_alive = False); a death event is emitted.

Extension point:
- Health engine will add sickness-spread logic after this stage.
- Season modifier (e.g. winter increases consumption) hooks in here.
"""
from app.enums import EventType, ResourceType
from app.simulation.types import AgentState, TurnContext, TurnEventRecord

HUNGER_INCREASE_PER_TURN = 0.15
# Reduced from 1.3 → sickness makes agents eat slightly more (fever/recovery),
# but they rest more so it's not a 30% spike. 1.1 prevents the death spiral
# where sick agents deplete food and die before being healed.
SICKNESS_HUNGER_MULTIPLIER = 1.1

# Sick agents spontaneously recover every SICKNESS_RECOVERY_PERIOD turns
# (deterministic per-agent cycle). Expected illness = ~8 turns without a healer.
SICKNESS_RECOVERY_PERIOD = 9

# Elderly agents (age >= 55) recover twice as slowly from illness.
ELDERLY_AGE_THRESHOLD = 55
ELDERLY_RECOVERY_MULTIPLIER = 2

# After Year 1 (365 turns), elderly agents can spontaneously fall ill.
# Period is a prime so each agent's cycle is offset from others.
OLD_AGE_SICK_PERIOD = 89        # ~elderly sickness every ~89 turns after Year 1
OLD_AGE_TURN_THRESHOLD = 365

# After Year 2 (730 turns), ALL agents face long-term health decline.
LONG_TERM_SICK_PERIOD = 61      # ~general decline every ~61 turns after Year 2
LONG_TERM_TURN_THRESHOLD = 730

# ---------------------------------------------------------------------------
# Risk Diversification constants
# ---------------------------------------------------------------------------

# Occupational Fatigue: farmer/blacksmith working 5+ consecutive turns without rest.
OCCUPATIONAL_FATIGUE_THRESHOLD = 5      # consecutive work turns before fatigue
OCCUPATIONAL_FATIGUE_PER_TURN = 0.02   # max_health loss per turn above threshold
_FATIGUE_PROFESSIONS = frozenset({"farmer", "blacksmith"})

# Long-term max_health decay (all agents, after Year 2).
MAX_HEALTH_DECAY_PER_TURN = 0.005      # 0.5% per turn
MAX_HEALTH_FLOOR = 0.3                  # minimum max_health ceiling

# Sickness lethality scaling: death probability grows with duration.
# P(death per turn) = min(CAP, days_sick * SEVERITY / constitution)
SICKNESS_DEATH_SEVERITY = 0.03         # base probability per day sick
SICKNESS_DEATH_CAP = 0.5               # maximum per-turn sickness death probability

# Profession-specific obituaries — deterministic, shown in the Chronicle.
_OBITUARY: dict[str, str] = {
    "farmer":     "{name}, the village's faithful farmer, has died. The fields will miss their steady hand.",
    "healer":     "{name}, who tended the sick and wounded, has passed away. The village is left without its healer.",
    "blacksmith": "{name}, who forged tools for the whole village, has died. The forge grows cold and quiet.",
    "merchant":   "{name}, who kept the village's trade alive, has passed away. The market stalls stand empty.",
    "priest":     "{name}, keeper of the village's faith, has died. The chapel bell rings a slow toll of mourning.",
    "soldier":    "{name}, who stood watch over the village, has fallen. The gates are unguarded tonight.",
}

# Daily food consumption by profession (units per turn)
FOOD_CONSUMPTION: dict[str, float] = {
    "farmer": 0.8,
    "blacksmith": 1.2,
    "merchant": 1.0,
    "healer": 0.9,
    "priest": 0.7,
    "soldier": 1.3,
}


def refresh_agent(agent: AgentState, current_turn: int = 0) -> AgentState:
    if not agent.is_alive:
        return agent

    # --- Max health: decays from occupational fatigue and long-term aging ---
    new_max_health = agent.max_health

    # Occupational fatigue: farmer/blacksmith overworking reduces health ceiling.
    # Penalty scales with excess consecutive turns: more overwork = more damage this turn.
    if (agent.profession.value in _FATIGUE_PROFESSIONS
            and agent.consecutive_work_turns >= OCCUPATIONAL_FATIGUE_THRESHOLD):
        excess = agent.consecutive_work_turns - OCCUPATIONAL_FATIGUE_THRESHOLD + 1
        fatigue_penalty = OCCUPATIONAL_FATIGUE_PER_TURN * excess
        new_max_health = max(MAX_HEALTH_FLOOR, round(new_max_health - fatigue_penalty, 6))

    # Long-term age decay: after Year 2 all agents slowly become more fragile
    if current_turn >= LONG_TERM_TURN_THRESHOLD:
        new_max_health = max(MAX_HEALTH_FLOOR, round(new_max_health - MAX_HEALTH_DECAY_PER_TURN, 6))

    # --- Sickness tracking and lethality scaling ---
    new_days_sick = agent.days_sick
    sick_death = False
    if agent.is_sick:
        new_days_sick = agent.days_sick + 1
        death_prob = min(SICKNESS_DEATH_CAP, (new_days_sick * SICKNESS_DEATH_SEVERITY) / max(agent.constitution, 0.5))
        # Deterministic per-agent, per-turn hash — varied primes prevent synchronised deaths
        _sick_hash = (agent.id * 37 + current_turn * 19) % 1000
        sick_death = _sick_hash < int(death_prob * 1000)

    # --- Food consumption ---
    # Apply constitution multiplier: varies by world+agent seed (default 1.0).
    consumption = FOOD_CONSUMPTION.get(agent.profession.value, 1.0) * agent.constitution
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

    # Death check: starvation when hunger reaches max_health ceiling, OR sickness lethality
    starvation_death = new_hunger >= new_max_health
    is_alive = not starvation_death and not sick_death

    # Spontaneous recovery AFTER consumption is computed so the sick-multiplier
    # still applies this turn (healer gets credit for this turn's treatment).
    # Elderly agents take twice as long to recover — longer illness exposure.
    recovery_period = SICKNESS_RECOVERY_PERIOD
    if agent.age >= ELDERLY_AGE_THRESHOLD:
        recovery_period = SICKNESS_RECOVERY_PERIOD * ELDERLY_RECOVERY_MULTIPLIER
    recovered = (
        agent.is_sick
        and not sick_death
        and (agent.id * 5 + current_turn) % recovery_period == 0
    )

    if recovered:
        new_days_sick = 0

    # Old-age spontaneous sickness onset (after Year 1, agents 55+).
    # Deterministic per-agent cycle — different offset per agent_id keeps
    # outbreaks staggered rather than hitting all elders simultaneously.
    old_age_sick = (
        not agent.is_sick
        and agent.age >= ELDERLY_AGE_THRESHOLD
        and current_turn >= OLD_AGE_TURN_THRESHOLD
        and (agent.id * 17 + current_turn) % OLD_AGE_SICK_PERIOD == 0
    )

    # Long-term general health decline (after Year 2, affects everyone).
    # Models cumulative fatigue, minor ailments, and aging of younger adults.
    long_term_sick = (
        not agent.is_sick
        and not old_age_sick
        and current_turn >= LONG_TERM_TURN_THRESHOLD
        and (agent.id * 23 + current_turn) % LONG_TERM_SICK_PERIOD == 0
    )

    becomes_sick = old_age_sick or long_term_sick

    return agent.model_copy(update={
        "hunger": new_hunger,
        "is_alive": is_alive,
        "is_sick": False if recovered else (True if becomes_sick else agent.is_sick),
        "inventory": new_inventory,
        "max_health": new_max_health,
        "days_sick": new_days_sick,
    })


def refresh_agents(ctx: TurnContext) -> TurnContext:
    """Refresh all agents and emit death/sickness events for state changes."""
    current_turn = ctx.world_state.current_turn
    new_events: list[TurnEventRecord] = []
    updated_agents = []

    for agent in ctx.world_state.agents:
        was_alive = agent.is_alive
        was_sick = agent.is_sick
        updated = refresh_agent(agent, current_turn)
        updated_agents.append(updated)

        if was_alive and not updated.is_alive:
            obit = _OBITUARY.get(agent.profession.value, "{name} has died.").format(name=agent.name)
            # Distinguish cause: sickness death leaves hunger below max_health ceiling
            cause = "starvation" if updated.hunger >= updated.max_health else "sickness"
            new_events.append(TurnEventRecord(
                world_id=ctx.world_state.id,
                turn_number=current_turn,
                event_type=EventType.conflict,
                description=obit,
                agent_ids=[agent.id],
                details={"is_death": True, "cause": cause},
            ))

        # Emit a sickness event when old-age or long-term decline triggers
        if was_alive and not was_sick and updated.is_sick:
            if current_turn >= OLD_AGE_TURN_THRESHOLD:
                if agent.age >= ELDERLY_AGE_THRESHOLD:
                    desc = f"{agent.name}'s age is beginning to wear on them — they have fallen ill."
                else:
                    desc = f"Years of hard labour have taken their toll on {agent.name}, who has fallen ill."
                new_events.append(TurnEventRecord(
                    world_id=ctx.world_state.id,
                    turn_number=current_turn,
                    event_type=EventType.sickness,
                    description=desc,
                    agent_ids=[agent.id],
                    details={"agent_id": agent.id, "cause": "age"},
                ))

    updated_world = ctx.world_state.model_copy(update={"agents": updated_agents})
    return ctx.model_copy(update={
        "world_state": updated_world,
        "events": list(ctx.events) + new_events,
    })
