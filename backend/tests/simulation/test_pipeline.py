"""Tests for TurnPipeline — stage ordering, insertion, and execution flow."""
import pytest

from app.simulation.pipeline import TurnPipeline, build_default_pipeline
from app.simulation.types import TurnContext

from tests.simulation.conftest import make_world_state


# ---------------------------------------------------------------------------
# Pipeline construction
# ---------------------------------------------------------------------------


class TestTurnPipelineConstruction:
    def test_empty_pipeline_has_no_stages(self):
        p = TurnPipeline()
        assert len(p) == 0

    def test_append_adds_stages_in_order(self):
        p = TurnPipeline()
        p.append("a", lambda ctx: ctx)
        p.append("b", lambda ctx: ctx)
        assert p.stage_names == ["a", "b"]

    def test_insert_after_places_stage_correctly(self):
        p = TurnPipeline()
        p.append("a", lambda ctx: ctx)
        p.append("c", lambda ctx: ctx)
        p.insert_after("a", "b", lambda ctx: ctx)
        assert p.stage_names == ["a", "b", "c"]

    def test_insert_before_places_stage_correctly(self):
        p = TurnPipeline()
        p.append("b", lambda ctx: ctx)
        p.append("c", lambda ctx: ctx)
        p.insert_before("b", "a", lambda ctx: ctx)
        assert p.stage_names == ["a", "b", "c"]

    def test_insert_after_unknown_stage_raises(self):
        p = TurnPipeline()
        p.append("a", lambda ctx: ctx)
        with pytest.raises(ValueError, match="not found"):
            p.insert_after("z", "b", lambda ctx: ctx)

    def test_insert_before_unknown_stage_raises(self):
        p = TurnPipeline()
        p.append("a", lambda ctx: ctx)
        with pytest.raises(ValueError, match="not found"):
            p.insert_before("z", "b", lambda ctx: ctx)


# ---------------------------------------------------------------------------
# Pipeline execution
# ---------------------------------------------------------------------------


class TestTurnPipelineExecution:
    def test_stages_receive_and_return_context(self):
        visited = []

        def stage_a(ctx: TurnContext) -> TurnContext:
            visited.append("a")
            return ctx

        def stage_b(ctx: TurnContext) -> TurnContext:
            visited.append("b")
            return ctx

        p = TurnPipeline()
        p.append("a", stage_a)
        p.append("b", stage_b)

        world = make_world_state()
        ctx = TurnContext(world_state=world)
        p.run(ctx)

        assert visited == ["a", "b"]

    def test_stage_output_feeds_next_stage(self):
        """Each stage should see mutations from the previous stage."""
        seen_days = []

        def bump_day(ctx: TurnContext) -> TurnContext:
            ws = ctx.world_state.model_copy(
                update={"current_day": ctx.world_state.current_day + 10}
            )
            return ctx.model_copy(update={"world_state": ws})

        def record_day(ctx: TurnContext) -> TurnContext:
            seen_days.append(ctx.world_state.current_day)
            return ctx

        p = TurnPipeline()
        p.append("bump", bump_day)
        p.append("record", record_day)

        world = make_world_state(day=1)
        p.run(TurnContext(world_state=world))
        assert seen_days == [11]

    def test_empty_pipeline_returns_unchanged_context(self):
        p = TurnPipeline()
        world = make_world_state(day=5)
        ctx = TurnContext(world_state=world)
        result = p.run(ctx)
        assert result.world_state.current_day == 5

    def test_append_returns_pipeline_for_chaining(self):
        p = TurnPipeline()
        result = p.append("a", lambda ctx: ctx)
        assert result is p


# ---------------------------------------------------------------------------
# Default pipeline
# ---------------------------------------------------------------------------


class TestDefaultPipeline:
    def test_has_six_stages(self):
        p = build_default_pipeline()
        assert len(p) == 6

    def test_stage_names_in_canonical_order(self):
        p = build_default_pipeline()
        assert p.stage_names == [
            "advance_world",
            "refresh_agents",
            "generate_opportunities",
            "resolve_actions",
            "create_turn_events",
            "record_memories",
        ]

    def test_full_turn_runs_without_error(self):
        from tests.simulation.conftest import make_agent_state
        from app.models.db import Profession

        farmer = make_agent_state(
            agent_id=1,
            profession=Profession.farmer,
            goals=[{"type": "produce", "target": "food", "priority": 1}],
            food=10.0,
        )
        world = make_world_state(agents=[farmer])
        p = build_default_pipeline()
        ctx = TurnContext(world_state=world)
        result = p.run(ctx)
        assert result.world_state.current_day == 2  # advance_world ran

    def test_extension_stage_injected_between_existing(self):
        p = build_default_pipeline()
        side_effect = []

        def spy_stage(ctx: TurnContext) -> TurnContext:
            side_effect.append("ran")
            return ctx

        p.insert_after("refresh_agents", "spy", spy_stage)
        assert "spy" in p.stage_names
        assert p.stage_names.index("spy") == p.stage_names.index("generate_opportunities") - 1

        from tests.simulation.conftest import make_agent_state
        from app.models.db import Profession
        farmer = make_agent_state(agent_id=1, profession=Profession.farmer, food=10.0)
        world = make_world_state(agents=[farmer])
        p.run(TurnContext(world_state=world))
        assert side_effect == ["ran"]
