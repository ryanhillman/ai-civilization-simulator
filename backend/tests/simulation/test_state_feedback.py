"""
Tests for state-driven variation in opportunity generation.

Verifies that simulation outputs change meaningfully with world state:
- harvest yield follows the seasonal curve
- trade_goods coin base follows the seasonal demand curve
- bless_village is suppressed when the village is healthy
- bless_village is offered when any agent is hungry or sick
- patrol is suppressed outside scheduled turns and without threats
- patrol is offered on scheduled turns (turn % 3 == 0)
- patrol is offered when a theft rumor is active
- surplus farmer can select trade_food over harvest (goal-action routing)
- trade_food no longer scores as food-seeking for hungry agents
- craft_tools coin varies by season (highest winter, lowest summer)
- harvest food_gained decreases when stockpile is large (saturation)
- trade_goods coin varies with merchant's coin stock (state modifier)
- recent harvest memories reduce harvest_food score (repetition penalty)
"""
import pytest

from app.enums import EventType, Profession, Season
from app.simulation.pressure import score_opportunity
from app.simulation.stages.opportunity_gen import (
    _CRAFT_COIN_BY_SEASON,
    _HARVEST_YIELD_BY_SEASON,
    _TRADE_COIN_BASE_BY_SEASON,
    generate_opportunities,
)
from app.simulation.types import (
    AgentPressure,
    MemoryRecord,
    Opportunity,
    RumorRecord,
    TurnContext,
)

from tests.simulation.conftest import make_agent_state, make_world_state


# ---------------------------------------------------------------------------
# Seasonal harvest yield
# ---------------------------------------------------------------------------


class TestSeasonalHarvestYield:
    def _harvest_yield_for_season(self, season: Season) -> float:
        farmer = make_agent_state(agent_id=1, profession=Profession.farmer)
        world = make_world_state(agents=[farmer], season=season, day=15)
        ctx = TurnContext(world_state=world)
        ctx_out = generate_opportunities(ctx)
        opp = next(o for o in ctx_out.opportunities if o.action_type == "harvest_food")
        return opp.metadata["yield_base"]

    def test_summer_yield_is_highest(self):
        assert self._harvest_yield_for_season(Season.summer) == pytest.approx(
            _HARVEST_YIELD_BY_SEASON["summer"]
        )

    def test_winter_yield_is_lowest(self):
        assert self._harvest_yield_for_season(Season.winter) == pytest.approx(
            _HARVEST_YIELD_BY_SEASON["winter"]
        )

    def test_yield_increases_spring_to_summer(self):
        spring = self._harvest_yield_for_season(Season.spring)
        summer = self._harvest_yield_for_season(Season.summer)
        assert summer > spring

    def test_yield_decreases_summer_to_winter(self):
        summer = self._harvest_yield_for_season(Season.summer)
        winter = self._harvest_yield_for_season(Season.winter)
        assert winter < summer

    def test_all_four_seasons_have_distinct_yields(self):
        yields = {s: self._harvest_yield_for_season(s) for s in Season}
        assert len(set(yields.values())) == 4


# ---------------------------------------------------------------------------
# Seasonal trade_goods coin base
# ---------------------------------------------------------------------------


class TestSeasonalTradeYield:
    def _trade_base_for_season(self, season: Season) -> float:
        merchant = make_agent_state(
            agent_id=1, profession=Profession.merchant,
            goals=[{"type": "trade", "priority": 1}],
        )
        world = make_world_state(agents=[merchant], season=season, day=15)
        ctx = TurnContext(world_state=world)
        ctx_out = generate_opportunities(ctx)
        opp = next(o for o in ctx_out.opportunities if o.action_type == "trade_goods")
        return opp.metadata["coin_gain_base"]

    def test_winter_trade_base_is_highest(self):
        assert self._trade_base_for_season(Season.winter) == pytest.approx(
            _TRADE_COIN_BASE_BY_SEASON["winter"]
        )

    def test_summer_trade_base_is_lowest(self):
        assert self._trade_base_for_season(Season.summer) == pytest.approx(
            _TRADE_COIN_BASE_BY_SEASON["summer"]
        )

    def test_winter_earns_more_than_summer(self):
        assert self._trade_base_for_season(Season.winter) > self._trade_base_for_season(Season.summer)


# ---------------------------------------------------------------------------
# bless_village gating
# ---------------------------------------------------------------------------


class TestBlessVillageGating:
    def test_bless_village_not_offered_when_village_healthy(self):
        """A well-fed, healthy village gives the priest no reason to bless."""
        priest = make_agent_state(
            agent_id=1, profession=Profession.priest, hunger=0.0,
            goals=[{"type": "maintain", "priority": 1}],
        )
        farmer = make_agent_state(agent_id=2, hunger=0.0, is_sick=False)
        world = make_world_state(agents=[priest, farmer])
        ctx = TurnContext(world_state=world)
        ctx_out = generate_opportunities(ctx)

        bless_opps = [o for o in ctx_out.opportunities if o.action_type == "bless_village"]
        assert len(bless_opps) == 0

    def test_bless_village_offered_when_agent_is_sick(self):
        priest = make_agent_state(agent_id=1, profession=Profession.priest)
        sick_villager = make_agent_state(agent_id=2, is_sick=True)
        world = make_world_state(agents=[priest, sick_villager])
        ctx = TurnContext(world_state=world)
        ctx_out = generate_opportunities(ctx)

        bless_opps = [o for o in ctx_out.opportunities if o.action_type == "bless_village"]
        assert len(bless_opps) == 1

    def test_bless_village_offered_when_agent_is_hungry(self):
        priest = make_agent_state(agent_id=1, profession=Profession.priest, hunger=0.0)
        hungry_villager = make_agent_state(agent_id=2, hunger=0.5)
        world = make_world_state(agents=[priest, hungry_villager])
        ctx = TurnContext(world_state=world)
        ctx_out = generate_opportunities(ctx)

        bless_opps = [o for o in ctx_out.opportunities if o.action_type == "bless_village"]
        assert len(bless_opps) == 1

    def test_priest_has_quiet_activity_when_no_village_need(self):
        """When bless_village is suppressed the priest gets one quiet activity
        (pray / study / tend_garden — rotates on a 3-turn cycle)."""
        _QUIET = {"pray", "study", "tend_garden"}
        priest = make_agent_state(
            agent_id=1, profession=Profession.priest, hunger=0.0,
        )
        # Test all three turns in the cycle to confirm exactly one quiet opp each time
        for turn in range(3):
            world = make_world_state(agents=[priest], turn=turn)
            ctx = TurnContext(world_state=world)
            ctx_out = generate_opportunities(ctx)
            quiet_opps = [o for o in ctx_out.opportunities if o.action_type in _QUIET]
            assert len(quiet_opps) == 1, f"Expected 1 quiet activity on turn {turn}"


# ---------------------------------------------------------------------------
# Patrol gating
# ---------------------------------------------------------------------------


class TestPatrolGating:
    def test_patrol_offered_on_scheduled_turn(self):
        """turn % 3 == 0 → routine patrol offered."""
        soldier = make_agent_state(
            agent_id=1, profession=Profession.soldier,
            goals=[{"type": "protect", "priority": 1}],
        )
        world = make_world_state(agents=[soldier], turn=0)
        ctx = TurnContext(world_state=world)
        ctx_out = generate_opportunities(ctx)

        patrol_opps = [o for o in ctx_out.opportunities if o.action_type == "patrol"]
        assert len(patrol_opps) == 1

    def test_patrol_not_offered_on_non_scheduled_turn_without_threat(self):
        """turn % 3 != 0 and no threat → no patrol."""
        soldier = make_agent_state(
            agent_id=1, profession=Profession.soldier,
            goals=[{"type": "protect", "priority": 1}],
        )
        world = make_world_state(agents=[soldier], turn=1)  # 1 % 3 != 0
        ctx = TurnContext(world_state=world)
        ctx_out = generate_opportunities(ctx)

        patrol_opps = [o for o in ctx_out.opportunities if o.action_type == "patrol"]
        assert len(patrol_opps) == 0

    def test_patrol_offered_with_active_theft_rumor(self):
        """Active theft rumor triggers an out-of-schedule patrol."""
        soldier = make_agent_state(
            agent_id=1, profession=Profession.soldier,
        )
        farmer = make_agent_state(agent_id=2)
        theft_rumor = RumorRecord(
            source_agent_id=99,
            subject_agent_id=99,
            world_id=1,
            turn_created=0,
            turn_expires=20,
            rumor_type="theft",
            content="Someone stole bread.",
            known_by=[farmer.id],
        )
        world = make_world_state(agents=[soldier, farmer], turn=1)
        world = world.model_copy(update={"active_rumors": [theft_rumor]})
        ctx = TurnContext(world_state=world)
        ctx_out = generate_opportunities(ctx)

        patrol_opps = [o for o in ctx_out.opportunities if o.action_type == "patrol"]
        assert len(patrol_opps) == 1

    def test_patrol_not_offered_with_non_theft_rumor_off_schedule(self):
        """Sickness rumors do not trigger a patrol."""
        soldier = make_agent_state(agent_id=1, profession=Profession.soldier)
        sickness_rumor = RumorRecord(
            source_agent_id=2,
            subject_agent_id=2,
            world_id=1,
            turn_created=0,
            turn_expires=20,
            rumor_type="sickness",
            content="Someone is ill.",
            known_by=[2],
        )
        world = make_world_state(agents=[soldier], turn=1)
        world = world.model_copy(update={"active_rumors": [sickness_rumor]})
        ctx = TurnContext(world_state=world)
        ctx_out = generate_opportunities(ctx)

        patrol_opps = [o for o in ctx_out.opportunities if o.action_type == "patrol"]
        assert len(patrol_opps) == 0


# ---------------------------------------------------------------------------
# Trade food surplus scoring
# ---------------------------------------------------------------------------


class TestTradeFoodSurplusScoring:
    def _make_pressure(self, resource_pressure: float, total: float) -> AgentPressure:
        return AgentPressure(
            agent_id=1,
            hunger_pressure=0.0,
            resource_pressure=resource_pressure,
            sickness_pressure=0.0,
            social_pressure=0.0,
            memory_pressure=0.0,
            total=total,
        )

    def test_trade_food_scores_higher_than_harvest_when_food_abundant(self):
        """Surplus agent should prefer selling over harvesting more."""
        pressure = self._make_pressure(resource_pressure=0.05, total=0.05)
        trade_opp = Opportunity(agent_id=1, action_type="trade_food")
        harvest_opp = Opportunity(agent_id=1, action_type="harvest_food")

        trade_score = score_opportunity(trade_opp, pressure).score
        harvest_score = score_opportunity(harvest_opp, pressure).score
        assert trade_score > harvest_score

    def test_trade_food_surplus_bonus_not_applied_at_moderate_pressure(self):
        """Surplus bonus (resource_pressure < 0.2) must not fire at moderate pressure."""
        # resource_pressure = 0.3: not scarce enough for production bonus,
        # not abundant enough for surplus bonus → baseline 1.0
        pressure = self._make_pressure(resource_pressure=0.3, total=0.3)
        trade_opp = Opportunity(agent_id=1, action_type="trade_food")
        scored = score_opportunity(trade_opp, pressure)
        assert scored.score == pytest.approx(1.0)

    def test_trade_food_scores_lower_with_moderate_pressure_than_abundant(self):
        """Surplus bonus lifts trade_food above its moderate-pressure score."""
        abundant = self._make_pressure(resource_pressure=0.05, total=0.05)
        moderate = self._make_pressure(resource_pressure=0.3, total=0.3)
        trade_opp = Opportunity(agent_id=1, action_type="trade_food")

        score_abundant = score_opportunity(trade_opp, abundant).score
        score_moderate = score_opportunity(trade_opp, moderate).score
        assert score_abundant > score_moderate

    def test_trade_food_not_boosted_by_hunger(self):
        """Hungry agent should not score selling food highly (removed from _FOOD_SEEKING)."""
        pressure = AgentPressure(
            agent_id=1,
            hunger_pressure=0.8,
            resource_pressure=0.0,
            sickness_pressure=0.0,
            social_pressure=0.0,
            memory_pressure=0.0,
            total=0.8,
        )
        trade_opp = Opportunity(agent_id=1, action_type="trade_food")
        harvest_opp = Opportunity(agent_id=1, action_type="harvest_food")

        trade_score = score_opportunity(trade_opp, pressure).score
        harvest_score = score_opportunity(harvest_opp, pressure).score
        # Hungry agent should strongly prefer harvesting over selling
        assert harvest_score > trade_score


# ---------------------------------------------------------------------------
# Goal-action routing: produce includes trade_food
# ---------------------------------------------------------------------------


class TestProduceGoalIncludesTradeFood:
    def test_farmer_with_surplus_selects_trade_food(self):
        """
        When trade_food is available and food is abundant (low resource
        pressure), the farmer's 'produce' goal should resolve to trade_food
        because it scores higher than harvest_food.
        """
        from app.simulation.economy.trade import generate_trade_opportunities
        from app.simulation.pipeline import build_phase3_pipeline
        from app.simulation.pressure import compute_agent_pressure
        from app.simulation.runner import TurnRunner

        farmer = make_agent_state(
            agent_id=1,
            profession=Profession.farmer,
            food=30.0,   # well above 5-turn buffer: resource_pressure near 0
            coin=5.0,
            goals=[{"type": "produce", "target": "food", "priority": 1}],
        )
        hungry_merchant = make_agent_state(
            agent_id=2,
            profession=Profession.merchant,
            food=0.5,
            coin=20.0,
            hunger=0.0,
            goals=[{"type": "trade", "target": "profit", "priority": 1}],
        )
        world = make_world_state(agents=[farmer, hungry_merchant])
        runner = TurnRunner(pipeline=build_phase3_pipeline())
        result = runner.run_turn(world)

        farmer_action = next(
            a for a in result.resolved_actions if a.agent_id == farmer.id
        )
        assert farmer_action.action_type == "trade_food", (
            f"Expected farmer with food surplus to trade; got {farmer_action.action_type}"
        )


# ---------------------------------------------------------------------------
# Seasonal craft_tools coin variation
# ---------------------------------------------------------------------------


class TestSeasonalCraftCoin:
    def _craft_coin_for_season(self, season: Season) -> float:
        smith = make_agent_state(
            agent_id=1,
            profession=Profession.blacksmith,
            wood=10.0,
            goals=[{"type": "accumulate", "priority": 1}],
        )
        world = make_world_state(agents=[smith], season=season)
        ctx = TurnContext(world_state=world)
        ctx_out = generate_opportunities(ctx)
        opp = next(o for o in ctx_out.opportunities if o.action_type == "craft_tools")
        return opp.metadata["coin_gain"]

    def test_winter_craft_coin_is_highest(self):
        assert self._craft_coin_for_season(Season.winter) == pytest.approx(
            _CRAFT_COIN_BY_SEASON["winter"]
        )

    def test_summer_craft_coin_is_lowest(self):
        assert self._craft_coin_for_season(Season.summer) == pytest.approx(
            _CRAFT_COIN_BY_SEASON["summer"]
        )

    def test_winter_coin_exceeds_summer_coin(self):
        assert self._craft_coin_for_season(Season.winter) > self._craft_coin_for_season(Season.summer)

    def test_all_four_seasons_have_distinct_craft_coins(self):
        coins = {s: self._craft_coin_for_season(s) for s in Season}
        assert len(set(coins.values())) == 4


# ---------------------------------------------------------------------------
# Harvest saturation: food-rich farmer gets diminishing returns
# ---------------------------------------------------------------------------


class TestHarvestSaturation:
    def _run_harvest(self, food: float) -> float:
        """Return food_gained for a farmer with the given food stock."""
        from app.simulation.pipeline import build_phase3_pipeline
        from app.simulation.runner import TurnRunner

        farmer = make_agent_state(
            agent_id=1,
            profession=Profession.farmer,
            food=food,
            goals=[{"type": "produce", "priority": 1}],
            traits={"warmth": 0.8, "courage": 0.4, "greed": 0.2, "cunning": 0.2, "piety": 0.5},
        )
        world = make_world_state(agents=[farmer], season=Season.spring)
        runner = TurnRunner(pipeline=build_phase3_pipeline())
        result = runner.run_turn(world)
        action = next(a for a in result.resolved_actions if a.agent_id == 1)
        assert action.action_type == "harvest_food"
        return action.details["food_gained"]

    def test_baseline_harvest_with_low_food_stock(self):
        """Below surplus threshold (food=2.0): no saturation, full yield."""
        yield_low = self._run_harvest(food=2.0)
        yield_surplus = self._run_harvest(food=30.0)
        assert yield_low > yield_surplus

    def test_large_stockpile_reduces_yield(self):
        """food=30 is well above 5-turn buffer — yield should be noticeably reduced."""
        yield_surplus = self._run_harvest(food=30.0)
        # Spring base 6.0 + warmth bonus 0.4 = 6.4; with saturation must be < 6.4
        assert yield_surplus < 6.4

    def test_higher_stock_means_lower_yield(self):
        """Monotonically decreasing yield as stock grows beyond threshold."""
        y10 = self._run_harvest(food=10.0)
        y20 = self._run_harvest(food=20.0)
        y30 = self._run_harvest(food=30.0)
        assert y10 >= y20 >= y30


# ---------------------------------------------------------------------------
# Trade goods state modifier: coin stock affects earnings
# ---------------------------------------------------------------------------


class TestTradeGoodsStateSensitivity:
    def _run_trade(self, coin: float) -> float:
        """Return coin_gained for a merchant with the given coin stock."""
        from app.simulation.pipeline import build_phase3_pipeline
        from app.simulation.runner import TurnRunner

        merchant = make_agent_state(
            agent_id=1,
            profession=Profession.merchant,
            coin=coin,
            goals=[{"type": "trade", "priority": 1}],
            traits={"cunning": 0.9, "courage": 0.4, "greed": 0.7, "warmth": 0.4, "piety": 0.1},
        )
        world = make_world_state(agents=[merchant], season=Season.spring)
        runner = TurnRunner(pipeline=build_phase3_pipeline())
        result = runner.run_turn(world)
        action = next(a for a in result.resolved_actions if a.agent_id == 1)
        assert action.action_type == "trade_goods"
        return action.details["coin_gained"]

    def test_poor_merchant_earns_more_than_baseline(self):
        """coin < 5 → motivated bonus (+15%)."""
        earned = self._run_trade(coin=2.0)
        # Spring base 3.0, cunning 0.9 → 3.0 * 1.9 * 1.15 > 3.0 * 1.9
        assert earned > 3.0 * 1.9

    def test_rich_merchant_earns_less_than_baseline(self):
        """coin > 25 → complacency penalty (-10%)."""
        earned = self._run_trade(coin=30.0)
        assert earned < 3.0 * 1.9

    def test_poor_merchant_earns_more_than_rich_merchant(self):
        """Motivated < 5 coin always outearns complacent > 25 coin."""
        assert self._run_trade(coin=2.0) > self._run_trade(coin=30.0)

    def test_moderate_coin_uses_baseline_multiplier(self):
        """coin in [5, 25] → no state modifier (state_mult = 1.0)."""
        earned = self._run_trade(coin=15.0)
        assert earned == pytest.approx(3.0 * 1.9)


# ---------------------------------------------------------------------------
# Repetition penalty: recent harvest memories reduce harvest_food score
# ---------------------------------------------------------------------------


class TestRepetitionPenalty:
    def _harvest_score_with_memories(self, harvest_count: int) -> float:
        """Score of harvest_food opportunity with N harvest memories."""
        memories = [
            MemoryRecord(
                agent_id=1,
                world_id=1,
                turn_number=i,
                event_type=EventType.harvest,
                summary=f"Harvested food on turn {i}.",
                emotional_weight=0.2,
            )
            for i in range(harvest_count)
        ]
        farmer = make_agent_state(
            agent_id=1,
            profession=Profession.farmer,
            recent_memories=memories,
        )
        world = make_world_state(agents=[farmer])
        ctx = TurnContext(world_state=world)
        ctx_out = generate_opportunities(ctx)
        opp = next(o for o in ctx_out.opportunities if o.action_type == "harvest_food")
        return opp.score

    def test_no_memories_scores_full_baseline(self):
        score = self._harvest_score_with_memories(0)
        assert score == pytest.approx(1.0)

    def test_one_harvest_memory_reduces_score(self):
        assert self._harvest_score_with_memories(1) < self._harvest_score_with_memories(0)

    def test_three_harvest_memories_reduces_score_more_than_one(self):
        assert self._harvest_score_with_memories(3) < self._harvest_score_with_memories(1)

    def test_penalty_capped_at_three_repeats(self):
        """4+ memories should not penalize more than 3."""
        score_3 = self._harvest_score_with_memories(3)
        score_5 = self._harvest_score_with_memories(5)
        assert score_3 == pytest.approx(score_5)

    def test_score_never_drops_below_minimum(self):
        """Even with maximum penalty the score stays at 0.1 or above."""
        score = self._harvest_score_with_memories(10)
        assert score >= 0.1


# ---------------------------------------------------------------------------
# Village demand factor: food scarcity shifts trade_goods earnings
# ---------------------------------------------------------------------------


class TestVillageDemandFactor:
    """
    trade_goods outcomes respond to village hunger via demand_factor baked
    into opportunity metadata. Hunger is a time-integrated scarcity signal.
    """

    def test_hungry_village_increases_demand_factor(self):
        """High average hunger → demand_factor > 1.0 (scarcity premium)."""
        from app.simulation.stages.opportunity_gen import _village_demand_factor

        hungry = [make_agent_state(i, hunger=0.6) for i in range(1, 4)]
        content = [make_agent_state(i, hunger=0.0) for i in range(1, 4)]
        assert _village_demand_factor(hungry) > _village_demand_factor(content)

    def test_well_fed_village_is_neutral(self):
        """Zero average hunger → demand_factor == 1.0 (no premium, no discount)."""
        from app.simulation.stages.opportunity_gen import _village_demand_factor

        agents = [make_agent_state(i, hunger=0.0) for i in range(1, 5)]
        assert _village_demand_factor(agents) == pytest.approx(1.0)

    def test_hungry_village_earns_more_for_merchant(self):
        """Merchant trade revenue is higher when village hunger is elevated."""
        from app.simulation.pipeline import build_phase3_pipeline
        from app.simulation.runner import TurnRunner

        def run_trade(hunger: float) -> float:
            merchant = make_agent_state(
                agent_id=1,
                profession=Profession.merchant,
                coin=15.0,
                hunger=hunger,
                goals=[{"type": "trade", "priority": 1}],
                traits={"cunning": 0.9, "courage": 0.4, "greed": 0.7,
                        "warmth": 0.4, "piety": 0.1},
            )
            world = make_world_state(agents=[merchant], season=Season.spring)
            runner = TurnRunner(pipeline=build_phase3_pipeline())
            result = runner.run_turn(world)
            action = next(a for a in result.resolved_actions if a.agent_id == 1)
            return action.details["coin_gained"]

        # Village hungry (0.6) vs well-fed (0.0) — hungry should command premium
        assert run_trade(0.6) > run_trade(0.0)


# ---------------------------------------------------------------------------
# Personal comfort modifier: food stock affects trade_goods earnings
# ---------------------------------------------------------------------------


class TestPersonalComfortModifier:
    """
    trade_goods earnings vary with the trader's own food stock.

    A food-secure merchant (>= 15 units) is more focused: slight premium.
    A food-poor merchant (< 5 units) is distracted: slight penalty.
    At food=10 the modifier is exactly 1.0 — backward-compatible baseline.
    """

    def _run_trade_with_food(self, food: float, coin: float = 15.0) -> float:
        from app.simulation.pipeline import build_phase3_pipeline
        from app.simulation.runner import TurnRunner

        merchant = make_agent_state(
            agent_id=1,
            profession=Profession.merchant,
            food=food,
            coin=coin,
            goals=[{"type": "trade", "priority": 1}],
            traits={"cunning": 0.9, "courage": 0.4, "greed": 0.7,
                    "warmth": 0.4, "piety": 0.1},
        )
        world = make_world_state(agents=[merchant], season=Season.spring)
        runner = TurnRunner(pipeline=build_phase3_pipeline())
        result = runner.run_turn(world)
        action = next(a for a in result.resolved_actions if a.agent_id == 1)
        return action.details["coin_gained"]

    def test_food_ten_is_neutral_baseline(self):
        """food=10 start → food=9 after refresh (merchant consumes 1.0/turn).
        food=9 is the calibrated neutral point → personal_mult=1.0 → same as
        the existing baseline assertion in TestTradeGoodsStateSensitivity."""
        earned = self._run_trade_with_food(food=10.0)
        assert earned == pytest.approx(3.0 * 1.9)  # spring base * cunning

    def test_high_food_earns_more_than_baseline(self):
        """food >= 15 → personal_mult=1.05, slight premium."""
        assert self._run_trade_with_food(food=15.0) > self._run_trade_with_food(food=10.0)

    def test_low_food_earns_less_than_baseline(self):
        """food < 5 → personal_mult=0.95, slight penalty."""
        assert self._run_trade_with_food(food=2.0) < self._run_trade_with_food(food=10.0)

    def test_food_depleted_merchant_earns_less_than_food_secure(self):
        """Confirms the full spread: food-poor < food-neutral < food-secure."""
        poor = self._run_trade_with_food(food=2.0)
        neutral = self._run_trade_with_food(food=10.0)
        rich = self._run_trade_with_food(food=20.0)
        assert poor < neutral < rich

    def test_trade_outcome_varies_across_natural_food_range(self):
        """
        Coin output must differ across the natural food range Elena experiences
        (food=4 through food=14), confirming no fixed repeated value.
        """
        values = {f: self._run_trade_with_food(food=float(f)) for f in range(4, 15)}
        # At least 3 distinct coin values across this range
        assert len(set(values.values())) >= 3


# ---------------------------------------------------------------------------
# Rumor descriptions: no raw numeric values leak into gossip text
# ---------------------------------------------------------------------------


class TestRumorDescriptions:
    """
    Rumor content must use narrative language, not raw inventory numbers.

    Hoarding rumors use prose descriptors (plenty, great store, etc.) rather
    than exact food counts so the chronicle reads naturally.
    """

    def test_hoard_description_uses_prose_not_numbers(self):
        from app.simulation.social.gossip import _hoard_description

        for food_val in [10.0, 25.0, 35.0, 55.0]:
            desc = _hoard_description(food_val)
            # Must not contain a raw float or integer digit string
            import re
            assert not re.search(r"\b\d+(\.\d+)?\b", desc), (
                f"_hoard_description({food_val}) leaked a number: {desc!r}"
            )

    def test_hoard_description_varies_by_amount(self):
        """Different food thresholds produce different narrative labels."""
        from app.simulation.social.gossip import _hoard_description

        descs = {_hoard_description(v) for v in [10.0, 25.0, 36.0, 55.0]}
        assert len(descs) >= 3, "Expected at least 3 distinct hoard descriptions"

    def test_theft_rumor_content_is_narrative(self):
        """Theft rumors use agent names, not IDs or raw numbers."""
        from app.simulation.social.gossip import _rumors_from_actions
        from app.simulation.types import ResolvedAction

        farmer = make_agent_state(agent_id=1, name="Aldric")
        victim = make_agent_state(agent_id=2, name="Marta")
        world = make_world_state(agents=[farmer, victim])

        action = ResolvedAction(
            agent_id=1,
            action_type="steal_food",
            outcome="stole food",
            details={"food_stolen": 2.0, "victim_id": 2},
        )
        rumors = _rumors_from_actions([action], world)
        assert len(rumors) == 1
        content = rumors[0].content
        assert "Aldric" in content
        assert "Marta" in content
        # No raw numeric inventory values in the rumor text
        import re
        assert not re.search(r"\b\d+\.\d+\b", content), (
            f"Theft rumor leaked a decimal: {content!r}"
        )
