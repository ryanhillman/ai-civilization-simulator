"""
Economy engine — Phase 3 implementation.

Provides one pipeline stage:

  generate_economy_opportunities  (insert after "generate_opportunities")

This stage generates inter-agent food trade opportunities based on supply
surplus and buyer resource pressure.

Usage in build_phase3_pipeline():

    from app.simulation.economy import generate_economy_opportunities
    pipeline.insert_after(
        "generate_opportunities",
        "economy_opportunities",
        generate_economy_opportunities,
    )

Food and coin are the primary economy resources for Phase 3.
Wood and medicine are secondary and reserved for craft/heal respectively.
"""
from app.simulation.economy.trade import generate_trade_opportunities
from app.simulation.types import TurnContext


def generate_economy_opportunities(ctx: TurnContext) -> TurnContext:
    """
    Generate inter-agent trade opportunities and append to ctx.opportunities.

    Seller-initiated: agents with surplus food offer to agents with
    resource pressure >= 0.5. Price is season- and pressure-adjusted.
    """
    trade_opps = generate_trade_opportunities(
        agents=ctx.world_state.living_agents,
        pressures=ctx.pressures,
        season=ctx.world_state.current_season,
    )
    if not trade_opps:
        return ctx
    return ctx.model_copy(update={"opportunities": ctx.opportunities + trade_opps})
