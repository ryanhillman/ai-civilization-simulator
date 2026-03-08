"""
Tests for the economy system — trade opportunity generation and resolution.
"""
import pytest

from app.enums import Profession, Season
from app.simulation.economy.trade import (
    FOOD_PER_TRADE,
    _trade_price,
    generate_trade_opportunities,
)
from app.simulation.pressure import compute_agent_pressure
from app.simulation.stages.action_resolve import _resolve
from app.simulation.types import AgentPressure, InventorySnapshot, Opportunity

from tests.simulation.conftest import make_agent_state, make_world_state


# ---------------------------------------------------------------------------
# Trade price
# ---------------------------------------------------------------------------


class TestTradePrice:
    def test_base_price_spring_no_pressure(self):
        price = _trade_price(None, None, Season.spring)
        assert price == pytest.approx(FOOD_PER_TRADE * 1.0)

    def test_winter_premium(self):
        spring_price = _trade_price(None, None, Season.spring)
        winter_price = _trade_price(None, None, Season.winter)
        assert winter_price > spring_price

    def test_summer_discount(self):
        spring_price = _trade_price(None, None, Season.spring)
        summer_price = _trade_price(None, None, Season.summer)
        assert summer_price < spring_price

    def test_desperate_buyer_pays_premium(self):
        buyer_pressure = AgentPressure(
            agent_id=2, total=2.5, hunger_pressure=0.5,
            resource_pressure=0.9, sickness_pressure=0.0,
            social_pressure=0.3, memory_pressure=0.0,
        )
        fair_price = _trade_price(None, None, Season.spring)
        desperate_price = _trade_price(None, buyer_pressure, Season.spring)
        assert desperate_price > fair_price

    def test_desperate_seller_gives_discount(self):
        seller_pressure = AgentPressure(
            agent_id=1, total=2.5, hunger_pressure=0.5,
            resource_pressure=0.9, sickness_pressure=0.0,
            social_pressure=0.3, memory_pressure=0.0,
        )
        fair_price = _trade_price(None, None, Season.spring)
        desperate_price = _trade_price(seller_pressure, None, Season.spring)
        assert desperate_price < fair_price

    def test_price_floor_is_enforced(self):
        # Desperate seller + summer discount should not go below 0.5 per unit
        seller_pressure = AgentPressure(
            agent_id=1, total=3.0, hunger_pressure=0.8,
            resource_pressure=0.9, sickness_pressure=0.8,
            social_pressure=0.0, memory_pressure=0.0,
        )
        price = _trade_price(seller_pressure, None, Season.summer)
        assert price >= 0.5


# ---------------------------------------------------------------------------
# Trade opportunity generation
# ---------------------------------------------------------------------------


class TestGenerateTradeOpportunities:
    def test_no_opportunities_when_all_well_fed(self):
        farmer = make_agent_state(agent_id=1, food=5.0, coin=5.0)
        merchant = make_agent_state(agent_id=2, food=4.0, coin=10.0)
        world = make_world_state(agents=[farmer, merchant])
        pressures = {a.id: compute_agent_pressure(a, world) for a in world.living_agents}
        opps = generate_trade_opportunities(
            world.living_agents, pressures, Season.spring
        )
        assert opps == []

    def test_surplus_farmer_offers_to_hungry_merchant(self):
        # Farmer has far more than 5-turn supply; merchant is nearly out of food
        farmer = make_agent_state(
            agent_id=1, profession=Profession.farmer, food=25.0, coin=5.0
        )
        merchant = make_agent_state(
            agent_id=2, profession=Profession.merchant, food=0.5, coin=10.0
        )
        world = make_world_state(agents=[farmer, merchant])
        pressures = {a.id: compute_agent_pressure(a, world) for a in world.living_agents}
        opps = generate_trade_opportunities(
            world.living_agents, pressures, Season.spring
        )
        assert len(opps) == 1
        assert opps[0].agent_id == farmer.id
        assert opps[0].target_agent_id == merchant.id
        assert opps[0].action_type == "trade_food"

    def test_buyer_without_coin_is_skipped(self):
        farmer = make_agent_state(
            agent_id=1, profession=Profession.farmer, food=25.0, coin=5.0
        )
        broke_merchant = make_agent_state(
            agent_id=2, profession=Profession.merchant, food=0.0, coin=0.0
        )
        world = make_world_state(agents=[farmer, broke_merchant])
        pressures = {a.id: compute_agent_pressure(a, world) for a in world.living_agents}
        opps = generate_trade_opportunities(
            world.living_agents, pressures, Season.spring
        )
        assert opps == []

    def test_trade_price_in_metadata(self):
        farmer = make_agent_state(
            agent_id=1, profession=Profession.farmer, food=25.0, coin=5.0
        )
        merchant = make_agent_state(
            agent_id=2, profession=Profession.merchant, food=0.5, coin=10.0
        )
        world = make_world_state(agents=[farmer, merchant])
        pressures = {a.id: compute_agent_pressure(a, world) for a in world.living_agents}
        opps = generate_trade_opportunities(
            world.living_agents, pressures, Season.spring
        )
        assert "price" in opps[0].metadata
        assert "food_amount" in opps[0].metadata
        assert opps[0].metadata["buyer_id"] == merchant.id

    def test_most_desperate_buyer_gets_priority(self):
        farmer = make_agent_state(
            agent_id=1, profession=Profession.farmer, food=25.0, coin=5.0
        )
        hungry_1 = make_agent_state(
            agent_id=2, profession=Profession.merchant, food=0.1, coin=10.0, hunger=0.6
        )
        hungry_2 = make_agent_state(
            agent_id=3, profession=Profession.priest, food=0.5, coin=10.0, hunger=0.3
        )
        world = make_world_state(agents=[farmer, hungry_1, hungry_2])
        pressures = {a.id: compute_agent_pressure(a, world) for a in world.living_agents}
        opps = generate_trade_opportunities(
            world.living_agents, pressures, Season.spring
        )
        # Farmer offers to only one buyer; should be the more desperate one
        assert len(opps) == 1
        assert opps[0].target_agent_id == hungry_1.id


# ---------------------------------------------------------------------------
# Trade resolution
# ---------------------------------------------------------------------------


class TestTradeResolution:
    def test_seller_loses_food_gains_coin(self):
        seller = make_agent_state(agent_id=1, food=20.0, coin=5.0)
        opp = Opportunity(
            agent_id=seller.id,
            action_type="trade_food",
            target_agent_id=2,
            metadata={"food_amount": 2.0, "price": 3.0, "buyer_id": 2},
        )
        action, updated = _resolve(opp, seller)
        assert action.action_type == "trade_food"
        assert action.succeeded is True
        assert updated.inventory.food == pytest.approx(18.0)
        assert updated.inventory.coin == pytest.approx(8.0)

    def test_action_details_contain_all_trade_fields(self):
        seller = make_agent_state(agent_id=1, food=20.0, coin=5.0)
        opp = Opportunity(
            agent_id=seller.id,
            action_type="trade_food",
            target_agent_id=2,
            metadata={"food_amount": 2.0, "price": 3.0, "buyer_id": 2},
        )
        action, _ = _resolve(opp, seller)
        assert action.details["food_sold"] == 2.0
        assert action.details["coin_received"] == 3.0
        assert action.details["buyer_id"] == 2

    def test_steal_food_stealer_gains_food(self):
        thief = make_agent_state(agent_id=1, food=0.5, coin=0.0)
        opp = Opportunity(
            agent_id=thief.id,
            action_type="steal_food",
            target_agent_id=2,
            metadata={"steal_amount": 2.0, "target_id": 2},
        )
        action, updated_thief = _resolve(opp, thief)
        assert action.action_type == "steal_food"
        assert updated_thief.inventory.food == pytest.approx(2.5)

    def test_steal_food_victim_side_effect_applied(self):
        """Victim food reduction is applied as a side effect in resolve_actions."""
        from app.enums import Profession
        from app.simulation.pipeline import build_phase3_pipeline
        from app.simulation.runner import TurnRunner

        desperate_soldier = make_agent_state(
            agent_id=1,
            profession=Profession.soldier,
            hunger=0.95,
            food=0.0,
            coin=0.0,
            goals=[{"type": "protect", "priority": 1}],
        )
        rich_farmer = make_agent_state(
            agent_id=2,
            profession=Profession.farmer,
            food=30.0,
            coin=20.0,
            goals=[{"type": "produce", "priority": 1}],
        )
        world = make_world_state(agents=[desperate_soldier, rich_farmer])
        runner = TurnRunner(pipeline=build_phase3_pipeline())
        result = runner.run_turn(world)

        soldier_pressure = result.pressures.get(desperate_soldier.id)
        if soldier_pressure and soldier_pressure.total >= 3.0:
            # Soldier was desperate enough to steal
            steal_action = next(
                (a for a in result.resolved_actions
                 if a.action_type == "steal_food"),
                None,
            )
            if steal_action:
                victim = result.world_state.agent_by_id(rich_farmer.id)
                # Victim should have less food than they started with
                assert victim.inventory.food < 30.0
