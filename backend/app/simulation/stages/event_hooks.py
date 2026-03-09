"""
Stage 5 — Event Hooks

Converts resolved actions into TurnEventRecord entries.
Only notable actions become events (rest and pray are suppressed).

Phase 3 additions: trade_food, steal_food mapped to appropriate event types.

Extension points:
- Economy engine: inject market-crash / shortage events
- Social engine: inject gossip / conflict / alliance events
- Health engine: inject outbreak / death events
- Weather engine: inject weather-driven events (drought, blizzard)

LLM integration (Phase 6+): the narrative field of TurnEvent is populated
here with a placeholder; the LLM enricher runs as a separate async pass
after the synchronous pipeline completes.
"""
from app.enums import EventType
from app.simulation.types import ResolvedAction, TurnContext, TurnEventRecord, WorldState


def _agent_name(world: WorldState, agent_id: int) -> str:
    """Resolve agent_id to display name; falls back to 'a villager' if not found."""
    agent = world.agent_by_id(agent_id)
    return agent.name if agent else "a villager"

_ACTION_TO_EVENT_TYPE: dict[str, EventType] = {
    "harvest_food":  EventType.harvest,
    "craft_tools":   EventType.trade,
    "trade_goods":   EventType.trade,
    "trade_food":    EventType.trade,
    "steal_food":    EventType.theft,
    "heal_self":     EventType.sickness,
    "heal_agent":    EventType.sickness,
    "pray":          EventType.rest,
    "bless_village": EventType.festival,
    "patrol":        EventType.rest,
}

# Actions too mundane to surface as timeline events
_SILENT_ACTIONS = {"rest", "pray", "patrol"}


def _action_to_event(
    action: ResolvedAction,
    world_id: int,
    turn: int,
    world: WorldState,
) -> TurnEventRecord | None:
    if action.action_type in _SILENT_ACTIONS:
        return None
    event_type = _ACTION_TO_EVENT_TYPE.get(action.action_type)
    if event_type is None:
        return None

    # Build agent_ids — include target for theft and trade
    agent_ids = [action.agent_id]
    target_id = (
        action.details.get("buyer_id")
        or action.details.get("victim_id")
        or action.details.get("healed_agent_id")
    )
    if target_id and target_id not in agent_ids:
        agent_ids.append(target_id)

    return TurnEventRecord(
        world_id=world_id,
        turn_number=turn,
        event_type=event_type,
        description=f"{_agent_name(world, action.agent_id)} {action.outcome}.",
        agent_ids=agent_ids,
        details=action.details,
    )


def create_turn_events(ctx: TurnContext) -> TurnContext:
    """
    Extension point: economy/social/health engines prepend or append events
    via pipeline stages inserted before or after this one.
    """
    events: list[TurnEventRecord] = list(ctx.events)
    ws = ctx.world_state
    for action in ctx.resolved_actions:
        event = _action_to_event(action, ws.id, ws.current_turn, ws)
        if event:
            events.append(event)
    return ctx.model_copy(update={"events": events})
