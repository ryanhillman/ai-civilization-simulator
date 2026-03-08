"""
Social engine — extension point.

Phase 2: stub only.

To inject social logic into the pipeline:

    from app.simulation.social import update_relationships, spread_gossip
    pipeline.insert_after("resolve_actions", "update_relationships", update_relationships)
    pipeline.insert_after("update_relationships", "spread_gossip", spread_gossip)

Planned subsystems (Phase 5+):
- Relationship delta updates after every interaction (trust, warmth, resentment)
- Alliance formation and grudge activation based on threshold crossing
- Gossip propagation: agents share observed events with trusted neighbours
- Rumor creation and credibility decay
"""
from app.simulation.types import TurnContext


def update_relationships(ctx: TurnContext) -> TurnContext:
    """Placeholder: adjust relationship scores based on this turn's interactions."""
    return ctx


def spread_gossip(ctx: TurnContext) -> TurnContext:
    """Placeholder: propagate rumours between agents who share high trust."""
    return ctx
