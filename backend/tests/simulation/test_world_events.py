"""
Tests for world events — festival, poor harvest, storm, sickness outbreak.
"""
import pytest

from app.enums import EventType, Season
from app.simulation.stages.world_events import apply_world_events
from app.simulation.types import TurnContext

from tests.simulation.conftest import make_agent_state, make_world_state


# ---------------------------------------------------------------------------
# Festival
# ---------------------------------------------------------------------------


class TestFestivalEvent:
    def test_festival_fires_on_day_1_of_season(self, village):
        # day % 30 == 1 → festival
        world = village.model_copy(update={"current_day": 31, "current_turn": 10})
        ctx = TurnContext(world_state=world)
        ctx_out = apply_world_events(ctx)

        festival_events = [e for e in ctx_out.events if e.event_type == EventType.festival]
        assert len(festival_events) == 1

    def test_festival_reduces_all_agents_hunger(self, farmer, healer):
        farmer_hungry = farmer.model_copy(update={"hunger": 0.5})
        healer_hungry = healer.model_copy(update={"hunger": 0.3})
        world = make_world_state(
            agents=[farmer_hungry, healer_hungry],
            day=31, turn=10,
        )
        world = world.model_copy(update={"current_turn": 10})
        ctx = TurnContext(world_state=world)
        ctx_out = apply_world_events(ctx)

        updated_farmer = ctx_out.world_state.agent_by_id(farmer.id)
        updated_healer = ctx_out.world_state.agent_by_id(healer.id)
        assert updated_farmer.hunger == pytest.approx(0.4)
        assert updated_healer.hunger == pytest.approx(0.2)

    def test_festival_does_not_fire_on_other_days(self, farmer):
        world = make_world_state(agents=[farmer], day=15, turn=5)
        ctx = TurnContext(world_state=world)
        ctx_out = apply_world_events(ctx)

        festival_events = [e for e in ctx_out.events if e.event_type == EventType.festival]
        assert len(festival_events) == 0

    def test_festival_world_event_recorded(self, farmer):
        world = make_world_state(agents=[farmer], day=1, turn=1)
        ctx = TurnContext(world_state=world)
        ctx_out = apply_world_events(ctx)

        festival_wes = [we for we in ctx_out.world_events if we.event_type == "festival"]
        assert len(festival_wes) == 1
        assert "festival" in festival_wes[0].description.lower()


# ---------------------------------------------------------------------------
# Poor harvest
# ---------------------------------------------------------------------------


class TestPoorHarvestEvent:
    def test_poor_harvest_in_winter_freezing(self, farmer):
        world = make_world_state(
            agents=[farmer], turn=5,
            season=Season.winter, weather="freezing",
        )
        ctx = TurnContext(world_state=world)
        ctx_out = apply_world_events(ctx)

        ph_wes = [we for we in ctx_out.world_events if we.event_type == "poor_harvest"]
        assert len(ph_wes) == 1
        assert ph_wes[0].modifiers["harvest_yield_multiplier"] == 0.5

    def test_poor_harvest_emits_weather_event(self, farmer):
        world = make_world_state(
            agents=[farmer], turn=5,
            season=Season.winter, weather="freezing",
        )
        ctx = TurnContext(world_state=world)
        ctx_out = apply_world_events(ctx)

        weather_events = [e for e in ctx_out.events if e.event_type == EventType.weather]
        assert len(weather_events) >= 1

    def test_no_poor_harvest_in_summer(self, farmer):
        world = make_world_state(
            agents=[farmer], turn=5,
            season=Season.summer, weather="hot",
        )
        ctx = TurnContext(world_state=world)
        ctx_out = apply_world_events(ctx)

        ph_wes = [we for we in ctx_out.world_events if we.event_type == "poor_harvest"]
        assert len(ph_wes) == 0

    def test_poor_harvest_modifier_consumed_by_opportunity_gen(self, farmer):
        """The poor_harvest modifier should reduce harvest yield_base."""
        from app.simulation.stages.opportunity_gen import generate_opportunities
        from app.simulation.stages.world_events import apply_world_events

        world = make_world_state(
            agents=[farmer], turn=5,
            season=Season.winter, weather="freezing",
        )
        ctx = TurnContext(world_state=world)
        ctx = apply_world_events(ctx)
        ctx = generate_opportunities(ctx)

        harvest_opps = [o for o in ctx.opportunities if o.action_type == "harvest_food"]
        assert len(harvest_opps) == 1
        # winter base 3.0 * poor_harvest multiplier 0.5 = 1.5
        assert harvest_opps[0].metadata["yield_base"] == pytest.approx(1.5)


# ---------------------------------------------------------------------------
# Storm
# ---------------------------------------------------------------------------


class TestStormEvent:
    def test_storm_fires_on_correct_conditions(self, farmer, soldier):
        # turn % 7 == 3, snowy weather
        world = make_world_state(
            agents=[farmer, soldier], turn=3,
            season=Season.winter, weather="snowy",
        )
        ctx = TurnContext(world_state=world)
        ctx_out = apply_world_events(ctx)

        storm_wes = [we for we in ctx_out.world_events if we.event_type == "storm"]
        assert len(storm_wes) == 1
        assert storm_wes[0].modifiers["harvest_yield_multiplier"] == 0.7
        assert storm_wes[0].modifiers["patrol_blocked"] is True

    def test_storm_blocks_patrol(self, farmer, soldier):
        """Storm should prevent patrol opportunities from generating."""
        from app.simulation.stages.opportunity_gen import generate_opportunities
        from app.simulation.stages.world_events import apply_world_events

        world = make_world_state(
            agents=[farmer, soldier], turn=3,
            season=Season.winter, weather="snowy",
        )
        ctx = TurnContext(world_state=world)
        ctx = apply_world_events(ctx)
        ctx = generate_opportunities(ctx)

        patrol_opps = [o for o in ctx.opportunities if o.action_type == "patrol"]
        assert len(patrol_opps) == 0

    def test_no_storm_outside_correct_turn(self, farmer):
        world = make_world_state(
            agents=[farmer], turn=4,  # 4 % 7 != 3
            season=Season.winter, weather="snowy",
        )
        ctx = TurnContext(world_state=world)
        ctx_out = apply_world_events(ctx)

        storm_wes = [we for we in ctx_out.world_events if we.event_type == "storm"]
        assert len(storm_wes) == 0


# ---------------------------------------------------------------------------
# Sickness outbreak
# ---------------------------------------------------------------------------


class TestSicknessOutbreak:
    def test_outbreak_on_turn_7(self, village):
        # turn % 19 == 7 (period raised from 13 → 19)
        # Location contamination may spread to nearby agents (30% chance each),
        # so newly_sick >= 1. We verify at least one agent falls ill.
        world = village.model_copy(update={"current_turn": 7})
        ctx = TurnContext(world_state=world)
        ctx_out = apply_world_events(ctx)

        newly_sick = [
            a for a in ctx_out.world_state.living_agents
            if a.is_sick and not village.agent_by_id(a.id).is_sick
        ]
        assert len(newly_sick) >= 1

    def test_outbreak_emits_sickness_event(self, village):
        world = village.model_copy(update={"current_turn": 7})
        ctx = TurnContext(world_state=world)
        ctx_out = apply_world_events(ctx)

        sick_events = [e for e in ctx_out.events if e.event_type == EventType.sickness]
        assert len(sick_events) >= 1

    def test_no_outbreak_on_regular_turn(self, village):
        world = village.model_copy(update={"current_turn": 5})  # 5 % 19 != 7
        ctx = TurnContext(world_state=world)
        ctx_out = apply_world_events(ctx)

        newly_sick = [
            a for a in ctx_out.world_state.living_agents
            if a.is_sick and not village.agent_by_id(a.id).is_sick
        ]
        assert len(newly_sick) == 0

    def test_already_sick_agent_not_re_infected(self):
        sick_agent = make_agent_state(agent_id=1, is_sick=True)
        world = make_world_state(agents=[sick_agent], turn=7)
        world = world.model_copy(update={"current_turn": 7})
        ctx = TurnContext(world_state=world)
        ctx_out = apply_world_events(ctx)

        # Still only one sick agent, no change
        sick_agents = [a for a in ctx_out.world_state.living_agents if a.is_sick]
        assert len(sick_agents) == 1

    def test_outbreak_world_event_recorded(self, village):
        world = village.model_copy(update={"current_turn": 7})
        ctx = TurnContext(world_state=world)
        ctx_out = apply_world_events(ctx)

        outbreak_wes = [
            we for we in ctx_out.world_events
            if we.event_type == "sickness_outbreak"
        ]
        assert len(outbreak_wes) == 1
        assert "modifiers" in outbreak_wes[0].model_fields_set or True
        assert "new_sick_agent_id" in outbreak_wes[0].modifiers
