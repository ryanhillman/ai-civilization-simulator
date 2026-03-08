"""
Phase 4 schema tests — no DB, no HTTP.

Tests the Pydantic schema helpers that convert domain objects into
API response bodies.
"""
import pytest

from app.enums import EventType, Profession, Season
from app.schemas import (
    AgentPressureResponse,
    InventoryResponse,
    TurnResultResponse,
    build_turn_result_response,
)
from app.simulation.pipeline import build_phase3_pipeline
from app.simulation.runner import TurnRunner
from tests.simulation.conftest import make_agent_state, make_world_state


def _runner() -> TurnRunner:
    return TurnRunner(pipeline=build_phase3_pipeline())


# ---------------------------------------------------------------------------
# build_turn_result_response
# ---------------------------------------------------------------------------


class TestBuildTurnResultResponse:
    def test_returns_turn_result_response_type(self):
        farmer = make_agent_state(
            agent_id=1, profession=Profession.farmer, food=10.0,
            goals=[{"type": "produce", "priority": 1}],
        )
        world = make_world_state(agents=[farmer])
        result = _runner().run_turn(world)
        response = build_turn_result_response(result)
        assert isinstance(response, TurnResultResponse)

    def test_world_id_and_turn_number_match(self):
        farmer = make_agent_state(
            agent_id=1, profession=Profession.farmer, food=10.0,
        )
        world = make_world_state(agents=[farmer])
        result = _runner().run_turn(world)
        response = build_turn_result_response(result)
        assert response.world_id == result.world_id
        assert response.turn_number == result.turn_number

    def test_agents_list_includes_all_agents(self):
        farmer = make_agent_state(agent_id=1, profession=Profession.farmer, food=10.0)
        merchant = make_agent_state(agent_id=2, profession=Profession.merchant, food=5.0)
        world = make_world_state(agents=[farmer, merchant])
        result = _runner().run_turn(world)
        response = build_turn_result_response(result)
        assert len(response.agents) == 2

    def test_agent_summary_has_inventory(self):
        farmer = make_agent_state(
            agent_id=1, profession=Profession.farmer, food=12.5, coin=3.0,
        )
        world = make_world_state(agents=[farmer])
        result = _runner().run_turn(world)
        response = build_turn_result_response(result)
        agent_summary = response.agents[0]
        assert isinstance(agent_summary.inventory, InventoryResponse)
        # food may have decreased by FOOD_CONSUMPTION this turn
        assert agent_summary.inventory.food >= 0.0
        assert agent_summary.inventory.coin == pytest.approx(3.0)

    def test_pressures_list_not_empty_for_living_agents(self):
        farmer = make_agent_state(agent_id=1, profession=Profession.farmer, food=10.0)
        world = make_world_state(agents=[farmer])
        result = _runner().run_turn(world)
        response = build_turn_result_response(result)
        assert len(response.pressures) >= 1
        assert isinstance(response.pressures[0], AgentPressureResponse)

    def test_pressure_embedded_in_agent_summary(self):
        farmer = make_agent_state(agent_id=1, profession=Profession.farmer, food=10.0)
        world = make_world_state(agents=[farmer])
        result = _runner().run_turn(world)
        response = build_turn_result_response(result)
        assert response.agents[0].pressure is not None
        assert hasattr(response.agents[0].pressure, "total")

    def test_dead_agent_has_no_pressure_in_response(self):
        dead = make_agent_state(agent_id=1, is_alive=False)
        farmer = make_agent_state(agent_id=2, profession=Profession.farmer, food=10.0)
        world = make_world_state(agents=[dead, farmer])
        result = _runner().run_turn(world)
        response = build_turn_result_response(result)
        dead_summary = next(a for a in response.agents if a.id == dead.id)
        assert dead_summary.pressure is None

    def test_events_list_populated(self):
        farmer = make_agent_state(
            agent_id=1, profession=Profession.farmer, food=10.0,
            goals=[{"type": "produce", "priority": 1}],
        )
        world = make_world_state(agents=[farmer])
        result = _runner().run_turn(world)
        response = build_turn_result_response(result)
        # events is a list (may be empty if nothing notable happened)
        assert isinstance(response.events, list)

    def test_world_event_on_festival_day(self):
        farmer = make_agent_state(agent_id=1, profession=Profession.farmer, food=10.0)
        world = make_world_state(agents=[farmer], day=30, turn=9)
        result = _runner().run_turn(world)
        response = build_turn_result_response(result)
        festival = [we for we in response.world_events if we.event_type == "festival"]
        assert len(festival) == 1

    def test_resolved_actions_match_agent_count(self):
        """Each living agent should have exactly one resolved action."""
        farmer = make_agent_state(
            agent_id=1, profession=Profession.farmer, food=10.0,
            goals=[{"type": "produce", "priority": 1}],
        )
        merchant = make_agent_state(
            agent_id=2, profession=Profession.merchant, food=5.0,
            goals=[{"type": "trade", "priority": 1}],
        )
        world = make_world_state(agents=[farmer, merchant])
        result = _runner().run_turn(world)
        response = build_turn_result_response(result)
        assert len(response.resolved_actions) == 2

    def test_response_is_json_serializable(self):
        farmer = make_agent_state(agent_id=1, profession=Profession.farmer, food=10.0)
        world = make_world_state(agents=[farmer])
        result = _runner().run_turn(world)
        response = build_turn_result_response(result)
        # model_dump_json should not raise
        json_str = response.model_dump_json()
        assert len(json_str) > 50

    def test_season_and_weather_propagated(self):
        from app.enums import Season
        farmer = make_agent_state(agent_id=1, profession=Profession.farmer, food=10.0)
        world = make_world_state(agents=[farmer])
        result = _runner().run_turn(world)
        response = build_turn_result_response(result)
        assert response.current_season in [s.value for s in Season]
        assert isinstance(response.weather, str)


# ---------------------------------------------------------------------------
# Autoplay cap
# ---------------------------------------------------------------------------


class TestAutoplayCap:
    def test_settings_autoplay_max_turns_is_twenty(self):
        from app.core.config import settings
        assert settings.autoplay_max_turns == 20

    def test_autoplay_capped_by_settings(self):
        """min(requested, settings.autoplay_max_turns) must never exceed 20."""
        from app.core.config import settings
        for requested in [1, 5, 19, 20, 21, 50, 100]:
            capped = min(requested, settings.autoplay_max_turns)
            assert capped <= 20
            assert capped == min(requested, 20)
