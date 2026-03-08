"""
Economy engine — extension point.

Phase 2: stub only.

To inject economy logic into the pipeline:

    from app.simulation.economy import generate_economy_opportunities, resolve_economy_actions
    pipeline.insert_after("generate_opportunities", "economy_opportunities", generate_economy_opportunities)
    pipeline.insert_after("resolve_actions", "economy_resolve", resolve_economy_actions)

Planned subsystems (Phase 4+):
- Market price fluctuation by season and supply/demand
- Barter and coin trade between agents
- Profession-based production chains (farmer → blacksmith → soldier)
- Scarcity events (drought, blight)
"""
from app.simulation.types import TurnContext


def generate_economy_opportunities(ctx: TurnContext) -> TurnContext:
    """Placeholder: inject economy-driven opportunities (market trades, etc.)."""
    return ctx


def resolve_economy_actions(ctx: TurnContext) -> TurnContext:
    """Placeholder: apply economy-level action effects (price changes, supply shifts)."""
    return ctx
