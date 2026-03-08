"""
Stage 3 — Opportunity Generation

Generates the set of actions each living agent may take this turn.
An Opportunity is a candidate action; actual selection happens in Stage 4.

Extension points:
- Economy engine: inject market-trade opportunities
- Social engine: inject alliance/gift/gossip opportunities
- Event engine: inject emergency response opportunities (fight fire, tend sick)

LLM integration (Phase 6+): the LLM will choose among these opportunities;
for now, Stage 4 selects deterministically.
"""
from app.enums import Profession
from app.simulation.types import AgentState, Opportunity, TurnContext


def _profession_opportunities(
    agent: AgentState,
    all_agents: list[AgentState],
) -> list[Opportunity]:
    aid = agent.id
    opps: list[Opportunity] = []

    # Universal: every agent can rest
    opps.append(Opportunity(agent_id=aid, action_type="rest"))

    profession = agent.profession

    if profession == Profession.farmer:
        opps.append(Opportunity(
            agent_id=aid,
            action_type="harvest_food",
            metadata={"yield_base": 3.0},
        ))

    elif profession == Profession.blacksmith:
        if agent.inventory.wood >= 2.0:
            opps.append(Opportunity(
                agent_id=aid,
                action_type="craft_tools",
                metadata={"wood_cost": 2.0, "coin_gain": 5.0},
            ))

    elif profession == Profession.merchant:
        opps.append(Opportunity(
            agent_id=aid,
            action_type="trade_goods",
            metadata={"coin_gain_base": 3.0},
        ))

    elif profession == Profession.healer:
        if agent.is_sick and agent.inventory.medicine >= 1.0:
            opps.append(Opportunity(
                agent_id=aid,
                action_type="heal_self",
                metadata={"medicine_cost": 1.0},
            ))
        # Heal up to 2 sick agents per turn
        sick_others = [
            a for a in all_agents
            if a.id != aid and a.is_alive and a.is_sick
        ]
        for sick in sick_others[:2]:
            if agent.inventory.medicine >= 1.0:
                opps.append(Opportunity(
                    agent_id=aid,
                    action_type="heal_agent",
                    target_agent_id=sick.id,
                    metadata={"medicine_cost": 1.0},
                ))

    elif profession == Profession.priest:
        opps.append(Opportunity(agent_id=aid, action_type="pray"))
        opps.append(Opportunity(agent_id=aid, action_type="bless_village"))

    elif profession == Profession.soldier:
        opps.append(Opportunity(agent_id=aid, action_type="patrol"))

    return opps


def generate_opportunities(ctx: TurnContext) -> TurnContext:
    """
    Extension point: economy/social/event engines append to ctx.opportunities
    via pipeline.insert_after("generate_opportunities", ...) before this stage,
    or by replacing this stage entirely.
    """
    all_agents = ctx.world_state.living_agents
    opps: list[Opportunity] = []
    for agent in all_agents:
        opps.extend(_profession_opportunities(agent, all_agents))
    return ctx.model_copy(update={"opportunities": opps})
