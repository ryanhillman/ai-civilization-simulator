"""Tests for Stage 1: world_advance — day, season, and weather progression."""
import pytest

from app.models.db import Season
from app.simulation.stages.world_advance import advance_world, day_to_season, DAYS_PER_SEASON
from app.simulation.types import TurnContext

from tests.simulation.conftest import make_world_state


# ---------------------------------------------------------------------------
# day_to_season
# ---------------------------------------------------------------------------


class TestDayToSeason:
    def test_spring_day_1(self):
        assert day_to_season(1) == Season.spring

    def test_spring_last_day(self):
        assert day_to_season(30) == Season.spring

    def test_summer_first_day(self):
        assert day_to_season(31) == Season.summer

    def test_summer_last_day(self):
        assert day_to_season(60) == Season.summer

    def test_autumn_first_day(self):
        assert day_to_season(61) == Season.autumn

    def test_autumn_last_day(self):
        assert day_to_season(90) == Season.autumn

    def test_winter_first_day(self):
        assert day_to_season(91) == Season.winter

    def test_winter_last_day(self):
        assert day_to_season(120) == Season.winter

    def test_wraps_to_spring_at_year_2(self):
        assert day_to_season(121) == Season.spring

    def test_wraps_to_summer_at_year_2(self):
        assert day_to_season(151) == Season.summer

    def test_wraps_at_large_day(self):
        # Day 361 = day 1 of year 4
        assert day_to_season(361) == Season.spring


# ---------------------------------------------------------------------------
# advance_world stage
# ---------------------------------------------------------------------------


class TestAdvanceWorld:
    def _run(self, world):
        ctx = TurnContext(world_state=world)
        return advance_world(ctx).world_state

    def test_day_increments_by_one(self):
        world = make_world_state(day=1)
        result = self._run(world)
        assert result.current_day == 2

    def test_day_increments_from_arbitrary_value(self):
        world = make_world_state(day=45)
        result = self._run(world)
        assert result.current_day == 46

    def test_season_stays_spring_mid_season(self):
        world = make_world_state(day=10, season=Season.spring)
        result = self._run(world)
        assert result.current_season == Season.spring

    def test_season_transitions_to_summer(self):
        # day 30 → advance to day 31 → summer
        world = make_world_state(day=30, season=Season.spring)
        result = self._run(world)
        assert result.current_day == 31
        assert result.current_season == Season.summer

    def test_season_transitions_autumn_to_winter(self):
        world = make_world_state(day=90, season=Season.autumn)
        result = self._run(world)
        assert result.current_season == Season.winter

    def test_season_wraps_winter_to_spring(self):
        world = make_world_state(day=120, season=Season.winter)
        result = self._run(world)
        assert result.current_day == 121
        assert result.current_season == Season.spring

    def test_weather_is_set(self):
        world = make_world_state(day=1)
        result = self._run(world)
        assert isinstance(result.weather, str)
        assert len(result.weather) > 0

    def test_weather_is_season_appropriate_spring(self):
        world = make_world_state(day=5)
        result = self._run(world)
        # Spring weather options: clear, rainy, cloudy, mild
        assert result.weather in {"clear", "rainy", "cloudy", "mild"}

    def test_weather_is_season_appropriate_winter(self):
        world = make_world_state(day=91)
        result = self._run(world)
        # Winter weather options: cold, snowy, freezing, overcast
        assert result.weather in {"cold", "snowy", "freezing", "overcast"}

    def test_weather_is_deterministic(self):
        """Same starting day always produces same weather."""
        world = make_world_state(day=15)
        r1 = self._run(world)
        r2 = self._run(world)
        assert r1.weather == r2.weather

    def test_input_world_not_mutated(self):
        world = make_world_state(day=10, season=Season.spring)
        original_day = world.current_day
        self._run(world)
        assert world.current_day == original_day

    def test_full_year_cycle(self):
        """Run 120 turns from day 1; verify we cycle back through all seasons."""
        world = make_world_state(day=1, season=Season.spring)
        ctx = TurnContext(world_state=world)
        seasons_seen = set()
        for _ in range(120):
            ctx = advance_world(ctx)
            seasons_seen.add(ctx.world_state.current_season)
        assert seasons_seen == {Season.spring, Season.summer, Season.autumn, Season.winter}
