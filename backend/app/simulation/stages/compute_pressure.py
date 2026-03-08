"""
Stage — Compute Agent Pressure

Runs after refresh_agents and before generate_opportunities.
Computes a deterministic AgentPressure for every living agent and stores
all profiles in TurnContext.pressures keyed by agent_id.

Downstream stages read ctx.pressures to:
  - score opportunities (generate_opportunities, economy_opportunities)
  - select actions     (resolve_actions — survival override at total >= 2.5)
  - generate rumors    (gossip — pressure triggers theft/hoarding rumors)

TurnResult.pressures exposes the full breakdown for debug output and
future LLM context.
"""
from app.simulation.pressure import compute_agent_pressure
from app.simulation.types import AgentPressure, TurnContext


def compute_pressure_stage(ctx: TurnContext) -> TurnContext:
    """
    Compute and store pressure for every living agent.

    Dead agents are skipped; their ids will be absent from ctx.pressures.
    """
    pressures: dict[int, AgentPressure] = {}
    for agent in ctx.world_state.living_agents:
        pressures[agent.id] = compute_agent_pressure(agent, ctx.world_state)
    return ctx.model_copy(update={"pressures": pressures})
