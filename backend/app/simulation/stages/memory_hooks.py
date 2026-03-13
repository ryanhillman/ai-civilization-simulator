"""
Stage 6 — Memory Hooks

Converts notable TurnEventRecords into MemoryRecord entries for each
involved agent.

Only events with |emotional_weight| >= MEMORY_THRESHOLD are recorded,
avoiding noise from low-significance actions.

Extension points:
- Social engine: add interpersonal memories (gossip heard, grudge formed)
- Health engine: add trauma memories for illness/death of close agents
- LLM integration (Phase 6+): replace summary template strings with
  LLM-generated first-person memories.
"""
from app.enums import EventType
from app.simulation.types import MemoryRecord, TurnContext, TurnEventRecord

MEMORY_THRESHOLD = 0.15

_EVENT_EMOTIONAL_WEIGHT: dict[EventType, float] = {
    EventType.harvest:  0.2,
    EventType.trade:    0.15,  # raised from 0.1 so trade/craft events are stored for repetition tracking
    EventType.sickness: -0.4,
    EventType.festival: 0.5,
    EventType.conflict: -0.6,
    EventType.gossip:   -0.15,
    EventType.weather:  0.0,
    EventType.rest:     0.0,
    EventType.theft:    -0.7,
}


def _event_to_memories(event: TurnEventRecord) -> list[MemoryRecord]:
    weight = _EVENT_EMOTIONAL_WEIGHT.get(event.event_type, 0.0)
    if abs(weight) < MEMORY_THRESHOLD:
        return []

    memories = []
    for agent_id in event.agent_ids:
        memories.append(MemoryRecord(
            agent_id=agent_id,
            world_id=event.world_id,
            turn_number=event.turn_number,
            event_type=event.event_type,
            summary=event.description,  # LLM will enrich this in Phase 6
            emotional_weight=weight,
        ))
    return memories


def record_memories(ctx: TurnContext) -> TurnContext:
    """
    Extension point: social engine appends interpersonal memories via a
    pipeline stage inserted after this one.
    """
    memories: list[MemoryRecord] = list(ctx.memories)
    for event in ctx.events:
        memories.extend(_event_to_memories(event))
    return ctx.model_copy(update={"memories": memories})
