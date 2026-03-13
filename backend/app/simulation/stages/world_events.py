"""
Stage — Apply World Events

Runs immediately after advance_world and before refresh_agents.
Computes deterministic world-level events from calendar, season, weather,
and turn number then applies their effects to world state.

All triggers are deterministic — same turn always produces same events.
World-ID is mixed into sickness targeting so different worlds produce
different victims, breaking the fixed Roland/Marta mortality order.

Events
------
  festival         Day 1 of each season (day % 30 == 1). Reduces all
                   agents' hunger by 0.1 and generates a festival event.

  poor_harvest     Winter + freezing weather. Harvest yield multiplier
                   drops to 0.5. Downstream: opportunity_gen reads the
                   modifier from ctx.world_events.

  storm            Snowy or freezing weather on turn % 7 == 3. Harvest
                   yield multiplier 0.7; patrol is flagged as blocked.

  sickness_outbreak  Turn % 19 == 7. One agent becomes sick, chosen via
                   hash(world_id, turn) so victim varies across worlds.

  cold_winter      Snowy or freezing winter. Agents with < 2 days of food
                   lose +0.03 hunger from cold exposure each qualifying
                   turn. Hits all professions equally — no one is immune
                   if they fail to maintain adequate food stocks.
"""
from __future__ import annotations

from app.enums import EventType, Profession
from app.simulation.stages.agent_refresh import FOOD_CONSUMPTION
from app.simulation.types import (
    AgentState,
    TurnContext,
    TurnEventRecord,
    WorldEventRecord,
    WorldState,
)

# ---------------------------------------------------------------------------
# Risk Diversification constants
# ---------------------------------------------------------------------------

# Healer protection: 70% resistance to sickness while actively treating patients.
HEALER_PROTECTION_FACTOR = 70   # out of 100

# Location contamination: when an outbreak hits the farm (farmer) or church
# (priest), nearby agents have this % chance of secondary infection.
LOCATION_SPREAD_CHANCE = 30     # out of 100

# Seasonal hardship: fires every 30 turns. Agents with < 5 days of food stock
# take a hunger penalty from cold / scarcity.
SEASONAL_HARDSHIP_PERIOD = 30
SEASONAL_HARDSHIP_FOOD_DAYS = 5.0   # days of supply threshold
SEASONAL_HARDSHIP_HUNGER = 0.15     # hunger penalty for under-stocked agents

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _festival_effect(world: WorldState, turn: int) -> tuple[WorldState, list[TurnEventRecord], list[WorldEventRecord]]:
    """Day 1 of each season: village festival reduces hunger slightly."""
    if world.current_day % 30 != 1:
        return world, [], []

    agents = [
        a.model_copy(update={"hunger": max(0.0, round(a.hunger - 0.1, 4))})
        if a.is_alive else a
        for a in world.agents
    ]
    living_ids = [a.id for a in world.living_agents]
    updated = world.model_copy(update={"agents": agents})

    we = WorldEventRecord(
        event_type="festival",
        description=f"The village celebrates the {world.current_season.value} festival!",
        affected_agent_ids=living_ids,
        modifiers={"hunger_reduction": 0.1},
    )
    event = TurnEventRecord(
        world_id=world.id,
        turn_number=turn,
        event_type=EventType.festival,
        description=we.description,
        agent_ids=living_ids,
    )
    return updated, [event], [we]


def _poor_harvest_effect(world: WorldState, turn: int) -> tuple[list[TurnEventRecord], list[WorldEventRecord]]:
    """Winter + freezing: record a poor_harvest modifier (consumed by opportunity_gen)."""
    if world.current_season.value != "winter" or world.weather != "freezing":
        return [], []

    we = WorldEventRecord(
        event_type="poor_harvest",
        description="Freezing temperatures have damaged the crops. Harvest yields are halved.",
        modifiers={"harvest_yield_multiplier": 0.5},
    )
    event = TurnEventRecord(
        world_id=world.id,
        turn_number=turn,
        event_type=EventType.weather,
        description=we.description,
        agent_ids=[],
        details={"modifier": "harvest_yield_multiplier=0.5"},
    )
    return [event], [we]


def _storm_effect(world: WorldState, turn: int) -> tuple[list[TurnEventRecord], list[WorldEventRecord]]:
    """Snowy/freezing weather on turn%7==3 causes a storm."""
    if world.weather not in ("snowy", "freezing"):
        return [], []
    if turn % 7 != 3:
        return [], []

    we = WorldEventRecord(
        event_type="storm",
        description="A fierce storm sweeps through the village.",
        modifiers={"harvest_yield_multiplier": 0.7, "patrol_blocked": True},
    )
    event = TurnEventRecord(
        world_id=world.id,
        turn_number=turn,
        event_type=EventType.weather,
        description=we.description,
        agent_ids=[],
        details={"modifier": "harvest_yield_multiplier=0.7"},
    )
    return [event], [we]


def _sickness_outbreak_effect(
    world: WorldState, turn: int
) -> tuple[WorldState, list[TurnEventRecord], list[WorldEventRecord]]:
    """Every 19 turns (turn % 19 == 7), a deterministic agent falls sick.

    Period raised from 13 → 19 to give sickness recovery time to work
    between outbreaks (~8-turn spontaneous recovery < 19-turn cycle).

    Healer immunity: the healer has 70% resistance when actively treating
    patients (medicine in stock + sick villagers present).

    Location contamination: if the victim is a farmer (Farm) or priest
    (Church), nearby agents have a 30% chance of secondary infection via
    deterministic hash — breaking the 'immortal four' pattern.
    """
    if turn % 19 != 7:
        return world, [], []

    living = world.living_agents
    if not living:
        return world, [], []

    # Mix world_id into the index so different worlds produce different victims.
    # FNV-1a-style 32-bit fold: robust distribution, no import overhead.
    _hash = ((world.id * 2654435761) ^ (turn * 40503)) & 0xFFFFFFFF
    target = living[_hash % len(living)]

    # Healer protection: if the healer is the target and has medicine with sick
    # villagers to treat, apply 70% immunity — punishing healers for doing their
    # job is counter-narrative.
    if target.profession == Profession.healer:
        has_sick_patients = any(a.is_sick and a.id != target.id for a in living)
        if has_sick_patients and target.inventory.medicine >= 1.0:
            immunity_check = (world.id * 41 + turn * 17) % 100
            if immunity_check < HEALER_PROTECTION_FACTOR:
                return world, [], []  # healer resists this outbreak

    if target.is_sick:
        return world, [], []

    agents = list(world.agents)
    newly_sick_ids = [target.id]

    # Apply primary infection
    for i, a in enumerate(agents):
        if a.id == target.id:
            agents[i] = a.model_copy(update={"is_sick": True})

    # Location contamination: farm (farmer victim) or church (priest victim)
    # spreads to nearby agents via a 30% deterministic exposure check.
    location_professions = {
        Profession.farmer: "Farm",
        Profession.priest: "Church",
    }
    if target.profession in location_professions:
        location_name = location_professions[target.profession]
        for i, a in enumerate(agents):
            if a.id == target.id or not a.is_alive or a.is_sick:
                continue
            # Healer has the same 70% resistance to location contamination.
            # Use the updated `agents` list so the newly-infected primary victim
            # counts as a sick patient (preventing healer from losing protection
            # immediately after an outbreak at their workplace).
            if a.profession == Profession.healer:
                has_sick_now = any(x.is_sick and x.id != a.id for x in agents if x.is_alive)
                if has_sick_now and a.inventory.medicine >= 1.0:
                    immunity_check = (world.id * 43 + turn * 11 + a.id * 7) % 100
                    if immunity_check < HEALER_PROTECTION_FACTOR:
                        continue  # healer resists location spread
            # 30% exposure check per agent
            exposure_check = (world.id * 43 + turn * 7 + a.id * 3) % 10
            if exposure_check < (LOCATION_SPREAD_CHANCE // 10):
                agents[i] = a.model_copy(update={"is_sick": True})
                newly_sick_ids.append(a.id)

    updated = world.model_copy(update={"agents": agents})
    all_events: list[TurnEventRecord] = []
    all_wes: list[WorldEventRecord] = []

    # Primary infection event
    primary_desc = f"{target.name} has fallen ill — sickness spreads through the village."
    all_wes.append(WorldEventRecord(
        event_type="sickness_outbreak",
        description=primary_desc,
        affected_agent_ids=newly_sick_ids,
        modifiers={"new_sick_agent_id": target.id},
    ))
    all_events.append(TurnEventRecord(
        world_id=world.id,
        turn_number=turn,
        event_type=EventType.sickness,
        description=primary_desc,
        agent_ids=[target.id],
        details={"agent_id": target.id},
    ))

    # Location contamination secondary events
    for sick_id in newly_sick_ids[1:]:
        sec_agent = world.agent_by_id(sick_id)
        if sec_agent:
            location_name = location_professions[target.profession]
            sec_desc = (
                f"{sec_agent.name} was exposed at the {location_name} "
                f"and has fallen ill."
            )
            all_events.append(TurnEventRecord(
                world_id=world.id,
                turn_number=turn,
                event_type=EventType.sickness,
                description=sec_desc,
                agent_ids=[sick_id],
                details={"agent_id": sick_id, "location": location_name},
            ))

    return updated, all_events, all_wes


_COLD_WINTER_WEATHERS = frozenset({"snowy", "freezing"})
# Hunger added per turn for under-stocked agents during cold winter.
_COLD_EXPOSURE_HUNGER = 0.03
# Minimum days of food stock below which an agent is exposed to cold.
_COLD_FOOD_DAYS_THRESHOLD = 2.0


def _cold_winter_effect(
    world: WorldState, turn: int
) -> tuple[WorldState, list[TurnEventRecord], list[WorldEventRecord]]:
    """Cold winter exposes agents with insufficient food to hunger drain.

    Fires every turn when it is winter and the weather is snowy or freezing.
    Any living agent whose food stock is below 2 days of their daily consumption
    gains +0.03 hunger from cold exposure. This applies equally to all
    professions — soldiers, priests, blacksmiths and merchants all suffer if
    they fail to maintain adequate food stores during winter.

    The effect is mild per turn but accumulates across a winter season,
    creating genuine long-term mortality risk beyond starvation alone.
    """
    if world.current_season.value != "winter":
        return world, [], []
    if world.weather not in _COLD_WINTER_WEATHERS:
        return world, [], []

    affected_ids: list[int] = []
    affected_names: list[str] = []
    agents = list(world.agents)

    for i, agent in enumerate(agents):
        if not agent.is_alive:
            continue
        daily = FOOD_CONSUMPTION.get(agent.profession.value, 1.0) * agent.constitution
        threshold = daily * _COLD_FOOD_DAYS_THRESHOLD
        if agent.inventory.food < threshold:
            new_hunger = min(1.0, round(agent.hunger + _COLD_EXPOSURE_HUNGER, 4))
            agents[i] = agent.model_copy(update={"hunger": new_hunger})
            affected_ids.append(agent.id)
            affected_names.append(agent.name)

    if not affected_ids:
        return world, [], []

    updated = world.model_copy(update={"agents": agents})

    name_list = ", ".join(affected_names[:3])
    if len(affected_names) > 3:
        name_list += f" and {len(affected_names) - 3} others"
    desc = (
        f"The bitter cold gnaws at the village. {name_list} "
        f"{'suffers' if len(affected_names) == 1 else 'suffer'} from exposure "
        f"without adequate food stores."
    )

    we = WorldEventRecord(
        event_type="cold_winter",
        description=desc,
        affected_agent_ids=affected_ids,
        modifiers={"cold_exposed_count": len(affected_ids)},
    )
    event = TurnEventRecord(
        world_id=world.id,
        turn_number=turn,
        event_type=EventType.weather,
        description=desc,
        agent_ids=affected_ids,
        details={"cold_exposed_count": len(affected_ids)},
    )
    return updated, [event], [we]


def _seasonal_hardship_effect(
    world: WorldState, turn: int
) -> tuple[WorldState, list[TurnEventRecord], list[WorldEventRecord]]:
    """Every 30 turns: agents with < 5 days of food stock suffer hunger.

    Models seasonal stock-taking — villagers who haven't maintained adequate
    stores suffer the consequences of scarcity regardless of profession.
    Fires at turn > 0 and turn % SEASONAL_HARDSHIP_PERIOD == 0.
    """
    if turn == 0 or turn % SEASONAL_HARDSHIP_PERIOD != 0:
        return world, [], []

    affected_ids: list[int] = []
    affected_names: list[str] = []
    agents = list(world.agents)

    for i, agent in enumerate(agents):
        if not agent.is_alive:
            continue
        daily = FOOD_CONSUMPTION.get(agent.profession.value, 1.0) * agent.constitution
        threshold = daily * SEASONAL_HARDSHIP_FOOD_DAYS
        if agent.inventory.food < threshold:
            new_hunger = min(1.0, round(agent.hunger + SEASONAL_HARDSHIP_HUNGER, 4))
            agents[i] = agent.model_copy(update={"hunger": new_hunger})
            affected_ids.append(agent.id)
            affected_names.append(agent.name)

    if not affected_ids:
        return world, [], []

    updated = world.model_copy(update={"agents": agents})
    name_list = ", ".join(affected_names[:3])
    if len(affected_names) > 3:
        name_list += f" and {len(affected_names) - 3} others"
    desc = (
        f"Seasonal hardship strikes — {name_list} "
        f"{'has' if len(affected_names) == 1 else 'have'} not maintained "
        f"adequate food stores and suffer from scarcity."
    )
    we = WorldEventRecord(
        event_type="seasonal_hardship",
        description=desc,
        affected_agent_ids=affected_ids,
        modifiers={"hardship_count": len(affected_ids)},
    )
    event = TurnEventRecord(
        world_id=world.id,
        turn_number=turn,
        event_type=EventType.weather,
        description=desc,
        agent_ids=affected_ids,
        details={"hardship_count": len(affected_ids)},
    )
    return updated, [event], [we]


# ---------------------------------------------------------------------------
# Stage entry point
# ---------------------------------------------------------------------------


def apply_world_events(ctx: TurnContext) -> TurnContext:
    """
    Apply all deterministic world events for this turn.

    Effects on agent state (hunger reduction, sickness) are applied directly.
    Harvest/patrol modifiers are stored in ctx.world_events for downstream
    stages to consume via:

        harvest_multiplier = next(
            (e.modifiers["harvest_yield_multiplier"] for e in ctx.world_events
             if "harvest_yield_multiplier" in e.modifiers),
            1.0
        )
    """
    world = ctx.world_state
    turn = world.current_turn
    all_events: list[TurnEventRecord] = list(ctx.events)
    all_world_events: list[WorldEventRecord] = list(ctx.world_events)

    # Festival
    world, fest_events, fest_wes = _festival_effect(world, turn)
    all_events.extend(fest_events)
    all_world_events.extend(fest_wes)

    # Poor harvest (modifier only, no direct state change)
    ph_events, ph_wes = _poor_harvest_effect(world, turn)
    all_events.extend(ph_events)
    all_world_events.extend(ph_wes)

    # Storm (modifier only)
    st_events, st_wes = _storm_effect(world, turn)
    all_events.extend(st_events)
    all_world_events.extend(st_wes)

    # Sickness outbreak
    world, sick_events, sick_wes = _sickness_outbreak_effect(world, turn)
    all_events.extend(sick_events)
    all_world_events.extend(sick_wes)

    # Cold winter (direct hunger drain on under-stocked agents)
    world, cold_events, cold_wes = _cold_winter_effect(world, turn)
    all_events.extend(cold_events)
    all_world_events.extend(cold_wes)

    # Seasonal hardship (every 30 turns: stock-check penalty for under-stocked agents)
    world, hard_events, hard_wes = _seasonal_hardship_effect(world, turn)
    all_events.extend(hard_events)
    all_world_events.extend(hard_wes)

    return ctx.model_copy(update={
        "world_state": world,
        "events": all_events,
        "world_events": all_world_events,
    })
