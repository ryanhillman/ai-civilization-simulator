"""
Health engine — extension point.

Phase 2: stub only.

To inject health logic into the pipeline:

    from app.simulation.health import apply_sickness_spread, apply_healing_effects
    pipeline.insert_after("refresh_agents", "sickness_spread", apply_sickness_spread)
    pipeline.insert_after("resolve_actions", "healing_effects", apply_healing_effects)

Planned subsystems (Phase 5+):
- Sickness spread probability based on proximity and season
- Disease progression (mild → severe → fatal)
- Healer effectiveness modifiers (medicine stock, skill level)
- Seasonal health modifiers (winter increases illness probability)
"""
from app.simulation.types import TurnContext


def apply_sickness_spread(ctx: TurnContext) -> TurnContext:
    """Placeholder: probabilistic sickness transmission between co-located agents."""
    return ctx


def apply_healing_effects(ctx: TurnContext) -> TurnContext:
    """Placeholder: apply lingering healing bonuses from healer actions."""
    return ctx
