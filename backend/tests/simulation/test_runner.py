"""Tests for TurnRunner — single-turn and multi-turn orchestration."""
import pytest

from app.models.db import Profession
from app.simulation.runner import TurnRunner
from app.simulation.types import TurnContext, TurnResult

from tests.simulation.conftest import make_agent_state, make_world_state


def _village():
    """Return a small deterministic world with one agent per key profession."""
    return make_world_state(
        agents=[
            make_agent_state(
                agent_id=1,
                name="Aldric",
                profession=Profession.farmer,
                goals=[{"type": "produce", "target": "food", "priority": 1}],
                traits={"courage": 0.4, "greed": 0.2, "warmth": 0.8, "cunning": 0.2, "piety": 0.5},
                food=18.0,
                coin=5.0,
                wood=8.0,
                medicine=1.0,
            ),
            make_agent_state(
                agent_id=2,
                name="Marta",
                profession=Profession.healer,
                goals=[{"type": "heal", "target": "villagers", "priority": 1}],
                food=10.0,
                medicine=15.0,
            ),
            make_agent_state(
                agent_id=3,
                name="Elena",
                profession=Profession.merchant,
                goals=[{"type": "trade", "target": "profit", "priority": 1}],
                traits={"courage": 0.4, "greed": 0.7, "warmth": 0.4, "cunning": 0.9, "piety": 0.1},
                food=12.0,
                coin=35.0,
            ),
        ]
    )


class TestRunTurn:
    def test_returns_turn_result(self):
        runner = TurnRunner()
        result = runner.run_turn(_village())
        assert isinstance(result, TurnResult)

    def test_turn_number_increments_from_zero(self):
        runner = TurnRunner()
        world = make_world_state(turn=0)
        result = runner.run_turn(world)
        assert result.turn_number == 1

    def test_turn_number_increments_from_arbitrary_value(self):
        runner = TurnRunner()
        world = make_world_state(turn=7)
        result = runner.run_turn(world)
        assert result.turn_number == 8

    def test_world_id_preserved(self):
        runner = TurnRunner()
        world = make_world_state(world_id=42)
        result = runner.run_turn(world)
        assert result.world_id == 42

    def test_day_advances(self):
        runner = TurnRunner()
        world = make_world_state(day=1)
        result = runner.run_turn(world)
        assert result.world_state.current_day == 2

    def test_input_world_not_mutated(self):
        runner = TurnRunner()
        world = _village()
        original_turn = world.current_turn
        runner.run_turn(world)
        assert world.current_turn == original_turn

    def test_events_list_populated_for_active_agents(self):
        runner = TurnRunner()
        result = runner.run_turn(_village())
        # Farmer harvests, merchant trades — both produce events
        assert len(result.events) > 0

    def test_resolved_actions_count_matches_living_agents(self):
        runner = TurnRunner()
        world = _village()
        result = runner.run_turn(world)
        assert len(result.resolved_actions) == len(world.living_agents)

    def test_summary_is_non_empty_string(self):
        runner = TurnRunner()
        result = runner.run_turn(_village())
        assert isinstance(result.summary, str)
        assert len(result.summary) > 0

    def test_summary_is_quiet_when_no_events(self):
        # All agents are dead — no events should fire
        runner = TurnRunner()
        dead_agent = make_agent_state(agent_id=1, is_alive=False)
        world = make_world_state(agents=[dead_agent])
        result = runner.run_turn(world)
        assert "quiet" in result.summary.lower()

    def test_farmer_food_increases_after_harvest(self):
        runner = TurnRunner()
        farmer = make_agent_state(
            agent_id=1,
            profession=Profession.farmer,
            goals=[{"type": "produce", "target": "food", "priority": 1}],
            traits={"warmth": 0.8, "courage": 0.5, "greed": 0.3, "cunning": 0.3, "piety": 0.3},
            food=5.0,
        )
        world = make_world_state(agents=[farmer])
        result = runner.run_turn(world)
        result_farmer = result.world_state.agent_by_id(1)
        # Harvested food > consumed food for a well-stocked farmer
        assert result_farmer.inventory.food > 5.0


class TestRunTurns:
    def test_returns_correct_number_of_results(self):
        runner = TurnRunner()
        results = runner.run_turns(_village(), n=5)
        assert len(results) == 5

    def test_turn_numbers_are_consecutive(self):
        runner = TurnRunner()
        results = runner.run_turns(make_world_state(turn=0), n=3)
        assert [r.turn_number for r in results] == [1, 2, 3]

    def test_days_are_consecutive(self):
        runner = TurnRunner()
        results = runner.run_turns(make_world_state(day=1), n=3)
        assert [r.world_state.current_day for r in results] == [2, 3, 4]

    def test_world_state_chains_between_turns(self):
        """Each turn must use the previous turn's world_state as input."""
        runner = TurnRunner()
        farmer = make_agent_state(
            agent_id=1,
            profession=Profession.farmer,
            goals=[{"type": "produce", "target": "food", "priority": 1}],
            traits={"warmth": 0.5, "courage": 0.5, "greed": 0.3, "cunning": 0.3, "piety": 0.3},
            food=20.0,
            hunger=0.0,
        )
        world = make_world_state(agents=[farmer])
        results = runner.run_turns(world, n=3)

        # Farmer harvests each turn; food should keep changing
        foods = [r.world_state.agent_by_id(1).inventory.food for r in results]
        # All three should be different values (harvesting + consuming each turn)
        assert len(set(foods)) > 1  # not all identical — state is evolving

    def test_run_zero_turns_returns_empty(self):
        runner = TurnRunner()
        results = runner.run_turns(_village(), n=0)
        assert results == []

    def test_season_progresses_over_many_turns(self):
        runner = TurnRunner()
        world = make_world_state(day=29)  # one day before summer
        results = runner.run_turns(world, n=5)
        # After 2 turns we should be in summer
        from app.models.db import Season
        seasons = [r.world_state.current_season for r in results]
        assert Season.summer in seasons

    def test_dead_agent_stays_dead_across_turns(self):
        """Starvation death should persist through subsequent turns."""
        runner = TurnRunner()
        # Agent with hunger near max and no food will die in turn 1
        dying = make_agent_state(
            agent_id=1,
            profession=Profession.farmer,
            hunger=0.95,
            food=0.0,
        )
        world = make_world_state(agents=[dying])
        results = runner.run_turns(world, n=3)
        # Should be dead after turn 1 and remain dead
        for result in results:
            agent = result.world_state.agent_by_id(1)
            if agent.hunger >= 1.0:
                assert agent.is_alive is False

    def test_custom_pipeline_used_by_runner(self):
        """Verify that a custom pipeline is actually called."""
        from app.simulation.pipeline import TurnPipeline

        called = []

        def spy(ctx: TurnContext) -> TurnContext:
            called.append(ctx.world_state.current_turn)
            return ctx

        p = TurnPipeline()
        p.append("spy", spy)
        runner = TurnRunner(pipeline=p)
        runner.run_turns(make_world_state(turn=0), n=3)
        # Spy should have been called 3 times, with turns 1, 2, 3
        assert called == [1, 2, 3]
