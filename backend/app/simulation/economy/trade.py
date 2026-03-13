"""
Economy — Trade Opportunity Generation

Generates inter-agent food trade opportunities.

Rules
-----
  Seller: agent with food > TRADE_SURPLUS_THRESHOLD (5 * daily consumption).
  Buyer:  agent with resource_pressure >= BUYER_PRESSURE_THRESHOLD (0.5).
  Price:  base 1.0 coin per food unit, modified by:
            - season (winter: 1.4×, summer: 0.9×, else 1.0×)
            - buyer pressure >= 2.0: buyer is desperate, +0.5 premium
            - seller pressure >= 2.0: seller is desperate, -0.3 discount

Each seller may offer to at most one buyer per turn (the most desperate one).
The buyer must have enough coin to afford the trade; otherwise skipped.

The trade_food Opportunity is seller-initiated. On resolution the seller
loses food and gains coin; the buyer gains food and loses coin (side-effect
in resolve_actions).
"""
from __future__ import annotations

from app.enums import Profession, Season
from app.simulation.pressure import score_opportunity
from app.simulation.stages.agent_refresh import FOOD_CONSUMPTION
from app.simulation.types import AgentPressure, AgentState, Opportunity, WorldState

TRADE_SURPLUS_THRESHOLD_TURNS = 3.5   # seller needs > 3.5 turns of food stock
# Merchant survival instinct: merchants refuse to sell food if their own supply
# is below a 5-turn survival buffer — they prioritise self-preservation.
MERCHANT_SURVIVAL_THRESHOLD_TURNS = 5.0
BUYER_PRESSURE_THRESHOLD = 0.35       # lowered from 0.5 — earlier intervention
FOOD_PER_TRADE = 2.0                  # food units transferred per trade
MAX_BUYERS_PER_SELLER = 2             # seller feeds up to 2 needy buyers per turn

# Only these professions produce food and may therefore offer it for sale.
# Non-producers (healer, priest, soldier, blacksmith) have finite starting stocks
# that must last them — they should never appear as sellers.
_FOOD_PRODUCING_PROFESSIONS = frozenset({Profession.farmer, Profession.merchant})

_SEASON_PRICE_MODIFIER: dict[str, float] = {
    "winter": 1.4,
    "autumn": 1.1,
    "spring": 1.0,
    "summer": 0.9,
}


def _trade_price(
    seller_pressure: AgentPressure | None,
    buyer_pressure: AgentPressure | None,
    season: Season,
) -> float:
    """
    Compute deterministic price per food unit for a trade.

    Desperate buyer pays a premium; desperate seller accepts a discount.
    Season shifts baseline supply/demand.
    """
    base = 1.0
    mod = _SEASON_PRICE_MODIFIER.get(season.value, 1.0)
    price = base * mod

    if buyer_pressure and buyer_pressure.total >= 2.0:
        price += 0.5   # desperate buyer pays more
    if seller_pressure and seller_pressure.total >= 2.0:
        price -= 0.3   # desperate seller accepts less

    return round(max(0.5, price) * FOOD_PER_TRADE, 2)


def generate_trade_opportunities(
    agents: list[AgentState],
    pressures: dict[int, AgentPressure],
    season: Season,
) -> list[Opportunity]:
    """
    Generate seller-initiated food trade opportunities.

    Returns a list of trade_food Opportunities to be appended to ctx.opportunities.
    Each opportunity is scored using the seller's pressure profile.
    """
    opps: list[Opportunity] = []

    # Identify needy buyers (sorted by pressure descending for match priority)
    needy_buyers = sorted(
        [
            a for a in agents
            if (p := pressures.get(a.id)) and p.resource_pressure >= BUYER_PRESSURE_THRESHOLD
        ],
        key=lambda a: -(pressures[a.id].total),
    )
    if not needy_buyers:
        return opps

    # For each potential seller, offer to up to MAX_BUYERS_PER_SELLER needy buyers.
    # Non-food-producers are excluded as sellers: they cannot replenish their stocks
    # and selling their buffer food would accelerate their own starvation.
    for seller in agents:
        if seller.profession not in _FOOD_PRODUCING_PROFESSIONS:
            continue

        daily = FOOD_CONSUMPTION.get(seller.profession.value, 1.0)
        # Merchant survival instinct: merchants use a higher survival threshold —
        # they refuse to trade food away if their personal supply is too low.
        threshold_turns = (
            MERCHANT_SURVIVAL_THRESHOLD_TURNS
            if seller.profession == Profession.merchant
            else TRADE_SURPLUS_THRESHOLD_TURNS
        )
        surplus_threshold = daily * threshold_turns

        if seller.inventory.food <= surplus_threshold:
            continue

        seller_pressure = pressures.get(seller.id)
        trades_made = 0

        for buyer in needy_buyers:
            if trades_made >= MAX_BUYERS_PER_SELLER:
                break
            if buyer.id == seller.id:
                continue

            buyer_pressure = pressures.get(buyer.id)
            price = _trade_price(seller_pressure, buyer_pressure, season)

            # Buyer must be able to afford the trade
            if buyer.inventory.coin < price:
                continue

            opp = Opportunity(
                agent_id=seller.id,
                action_type="trade_food",
                target_agent_id=buyer.id,
                metadata={
                    "food_amount": FOOD_PER_TRADE,
                    "price": price,
                    "buyer_id": buyer.id,
                },
            )
            opps.append(score_opportunity(opp, seller_pressure))
            trades_made += 1

    return opps
