"""
Stage — Apply World Events

Runs immediately after advance_world and before refresh_agents.
Computes deterministic world-level events from calendar, season, weather,
and turn number then applies their effects to world state.

All triggers are deterministic — same turn always produces same events.

Events
------
  festival         Day 1 of each season (day % 30 == 1). Reduces all
                   agents' hunger by 0.1 and generates a festival event.

  poor_harvest     Winter + freezing weather. Harvest yield multiplier
                   drops to 0.5. Downstream: opportunity_gen reads the
                   modifier from ctx.world_events.

  storm            Snowy or freezing weather on turn % 7 == 3. Harvest
                   yield multiplier 0.7; patrol is flagged as blocked.

  sickness_outbreak  Turn % 13 == 7. One deterministic agent becomes sick
                   (index = turn % len(living)). Creates a sickness event
                   and a rumor seed.
"""
from __future__ import annotations

from app.enums import EventType
from app.simulation.types import (
    AgentState,
    TurnContext,
    TurnEventRecord,
    WorldEventRecord,
    WorldState,
)

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
    """Every 13 turns (turn % 13 == 7), a deterministic agent falls sick."""
    if turn % 13 != 7:
        return world, [], []

    living = world.living_agents
    if not living:
        return world, [], []

    target = living[turn % len(living)]
    if target.is_sick:
        return world, [], []

    agents = [
        a.model_copy(update={"is_sick": True}) if a.id == target.id else a
        for a in world.agents
    ]
    updated = world.model_copy(update={"agents": agents})

    we = WorldEventRecord(
        event_type="sickness_outbreak",
        description=f"{target.name} has fallen ill — sickness spreads through the village.",
        affected_agent_ids=[target.id],
        modifiers={"new_sick_agent_id": target.id},
    )
    event = TurnEventRecord(
        world_id=world.id,
        turn_number=turn,
        event_type=EventType.sickness,
        description=we.description,
        agent_ids=[target.id],
        details={"agent_id": target.id},
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

    return ctx.model_copy(update={
        "world_state": world,
        "events": all_events,
        "world_events": all_world_events,
    })
