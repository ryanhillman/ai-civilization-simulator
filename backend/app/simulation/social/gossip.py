"""
Social — Gossip Propagation

Manages structured rumors: creation from notable events and spread
through agent trust networks.

Rumor creation
--------------
  steal_food   → theft rumor about the thief (credibility 0.8)
  sickness     → sickness rumor about the sick agent (credibility 0.6)
  hoarding     → rumor about agent with very high food stock while others
                 suffer high resource pressure (credibility 0.5)

Rumor spreading
---------------
  For each active rumor, find spreader→listener pairs where:
    - spreader knows the rumor (id in rumor.known_by)
    - trust[spreader → listener] >= GOSSIP_TRUST_THRESHOLD (0.4)
  Add listener to known_by. Each spread creates a gossip TurnEventRecord.

Rumor expiry
------------
  Rumors with turn_expires <= current_turn are pruned before processing.

Structured format
-----------------
  Rumor content uses templated strings, not free-form text, so it is
  inspectable and deterministic regardless of LLM availability.
"""
from __future__ import annotations

from app.enums import EventType
from app.simulation.types import (
    ResolvedAction,
    RumorRecord,
    TurnContext,
    TurnEventRecord,
    WorldState,
)

GOSSIP_TRUST_THRESHOLD = 0.4
RUMOR_TTL_TURNS = 10          # rumor expires after this many turns


def _agent_name(world: WorldState, agent_id: int) -> str:
    """Resolve agent_id to display name; falls back to 'a villager' if not found."""
    agent = world.agent_by_id(agent_id)
    return agent.name if agent else "a villager"


# ---------------------------------------------------------------------------
# Rumor creation
# ---------------------------------------------------------------------------


def _rumors_from_actions(
    actions: list[ResolvedAction],
    world: WorldState,
) -> list[RumorRecord]:
    """Create new rumors from this turn's resolved actions."""
    turn = world.current_turn
    new_rumors: list[RumorRecord] = []

    for action in actions:
        if not action.succeeded:
            continue

        if action.action_type == "steal_food":
            victim_id = action.details.get("victim_id")
            new_rumors.append(RumorRecord(
                source_agent_id=action.agent_id,
                subject_agent_id=action.agent_id,
                world_id=world.id,
                turn_created=turn,
                turn_expires=turn + RUMOR_TTL_TURNS,
                rumor_type="theft",
                content=(
                    f"{_agent_name(world, action.agent_id)} was seen stealing "
                    f"food from {_agent_name(world, victim_id)}."
                ),
                credibility=0.8,
                known_by=[action.agent_id],
            ))

        elif action.action_type in ("heal_agent", "heal_self"):
            patient_id = (
                action.details.get("healed_agent_id") or action.agent_id
            )
            # Sickness being treated is newsworthy
            agent = world.agent_by_id(patient_id)
            if agent:
                new_rumors.append(RumorRecord(
                    source_agent_id=action.agent_id,
                    subject_agent_id=patient_id,
                    world_id=world.id,
                    turn_created=turn,
                    turn_expires=turn + RUMOR_TTL_TURNS,
                    rumor_type="sickness",
                    content=f"{agent.name} has been seen ill.",
                    credibility=0.6,
                    known_by=[action.agent_id],
                ))

    return new_rumors


def _hoarding_rumors(world: WorldState) -> list[RumorRecord]:
    """
    Detect hoarding: an agent with food > 20 while others have resource
    pressure >= 0.7. One hoarding rumor per hoarder per turn at most.
    """
    turn = world.current_turn
    agents = world.living_agents
    if not agents:
        return []

    pressures_high = [
        a for a in agents if a.inventory.food < 2.0 and not a.is_sick
    ]
    if not pressures_high:
        return []

    new_rumors: list[RumorRecord] = []
    for agent in agents:
        if agent.inventory.food > 20.0:
            # Check this rumor isn't already active
            already = any(
                r.rumor_type == "hoarding"
                and r.subject_agent_id == agent.id
                and r.turn_expires > turn
                for r in world.active_rumors
            )
            if not already:
                new_rumors.append(RumorRecord(
                    source_agent_id=pressures_high[0].id,  # observed by neediest
                    subject_agent_id=agent.id,
                    world_id=world.id,
                    turn_created=turn,
                    turn_expires=turn + RUMOR_TTL_TURNS,
                    rumor_type="hoarding",
                    content=(
                        f"{agent.name} is hoarding "
                        f"{agent.inventory.food:.0f} food while others starve."
                    ),
                    credibility=0.5,
                    known_by=[pressures_high[0].id],
                ))
    return new_rumors


# ---------------------------------------------------------------------------
# Rumor spreading
# ---------------------------------------------------------------------------


def _spread_rumors(
    rumors: list[RumorRecord],
    world: WorldState,
    turn: int,
) -> tuple[list[RumorRecord], list[TurnEventRecord]]:
    """
    Propagate rumors through trust relationships.

    Returns updated rumor list and new gossip events.
    """
    updated_rumors: list[RumorRecord] = []
    gossip_events: list[TurnEventRecord] = []

    for rumor in rumors:
        knowers = set(rumor.known_by)
        new_knowers: set[int] = set()

        for rel in world.relationships:
            if (
                rel.source_agent_id in knowers
                and rel.target_agent_id not in knowers
                and rel.trust >= GOSSIP_TRUST_THRESHOLD
            ):
                new_knowers.add(rel.target_agent_id)

        if new_knowers:
            updated_rumors.append(rumor.model_copy(update={
                "known_by": list(knowers | new_knowers),
                "spread_count": rumor.spread_count + len(new_knowers),
            }))
            for listener_id in new_knowers:
                gossip_events.append(TurnEventRecord(
                    world_id=world.id,
                    turn_number=turn,
                    event_type=EventType.gossip,
                    description=(
                        f"{_agent_name(world, listener_id)} hears: \"{rumor.content}\""
                    ),
                    agent_ids=[listener_id, rumor.source_agent_id],
                    details={
                        "rumor_type": rumor.rumor_type,
                        "subject_id": rumor.subject_agent_id,
                        "credibility": rumor.credibility,
                    },
                ))
        else:
            updated_rumors.append(rumor)

    return updated_rumors, gossip_events


# ---------------------------------------------------------------------------
# Stage entry point
# ---------------------------------------------------------------------------


def spread_gossip(ctx: TurnContext) -> TurnContext:
    """
    Create new rumors from this turn's actions, spread existing ones,
    and prune expired rumors.

    Rumor state lives in WorldState.active_rumors and persists across turns.
    """
    world = ctx.world_state
    turn = world.current_turn

    # Prune expired rumors
    active = [r for r in world.active_rumors if r.turn_expires > turn]

    # Create new rumors from this turn's actions and hoarding detection
    new_from_actions = _rumors_from_actions(ctx.resolved_actions, world)
    new_from_hoarding = _hoarding_rumors(world)
    all_rumors = active + new_from_actions + new_from_hoarding

    # Spread
    spread_rumors, gossip_events = _spread_rumors(all_rumors, world, turn)

    updated_world = world.model_copy(update={"active_rumors": spread_rumors})
    return ctx.model_copy(update={
        "world_state": updated_world,
        "events": ctx.events + gossip_events,
    })
