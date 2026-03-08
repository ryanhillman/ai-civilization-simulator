"""
TurnPipeline

An ordered, named list of stage functions. Each stage has the signature:

    (TurnContext) -> TurnContext

Stages are applied in sequence; the output context of each stage becomes
the input of the next. This makes the pipeline easy to test in isolation
(call any stage directly) and easy to extend (insert_after / append).

Usage:

    pipeline = build_default_pipeline()
    ctx_out = pipeline.run(ctx_in)

Extending for economy:

    from app.simulation.economy import generate_economy_opportunities
    pipeline.insert_after(
        "generate_opportunities",
        "economy_opportunities",
        generate_economy_opportunities,
    )
"""
from __future__ import annotations

from typing import Callable

from app.simulation.types import TurnContext

Stage = Callable[[TurnContext], TurnContext]


class TurnPipeline:
    def __init__(self) -> None:
        self._stages: list[tuple[str, Stage]] = []

    # ------------------------------------------------------------------
    # Pipeline construction
    # ------------------------------------------------------------------

    def append(self, name: str, stage: Stage) -> "TurnPipeline":
        """Add a stage to the end of the pipeline."""
        self._stages.append((name, stage))
        return self

    def insert_after(self, after_name: str, name: str, stage: Stage) -> "TurnPipeline":
        """Insert a stage immediately after the named stage."""
        for i, (n, _) in enumerate(self._stages):
            if n == after_name:
                self._stages.insert(i + 1, (name, stage))
                return self
        raise ValueError(f"Stage '{after_name}' not found in pipeline")

    def insert_before(self, before_name: str, name: str, stage: Stage) -> "TurnPipeline":
        """Insert a stage immediately before the named stage."""
        for i, (n, _) in enumerate(self._stages):
            if n == before_name:
                self._stages.insert(i, (name, stage))
                return self
        raise ValueError(f"Stage '{before_name}' not found in pipeline")

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def stage_names(self) -> list[str]:
        return [name for name, _ in self._stages]

    def __len__(self) -> int:
        return len(self._stages)

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def run(self, ctx: TurnContext) -> TurnContext:
        for _name, stage in self._stages:
            ctx = stage(ctx)
        return ctx


# ---------------------------------------------------------------------------
# Default pipeline factory
# ---------------------------------------------------------------------------


def build_default_pipeline() -> TurnPipeline:
    """
    Build the canonical turn pipeline with all six core stages.

    Stage order:
      1. advance_world       — tick day, season, weather
      2. refresh_agents      — hunger, starvation check
      3. generate_opportunities — build action candidate list
      4. resolve_actions     — select + apply best action per agent
      5. create_turn_events  — convert actions to timeline events
      6. record_memories     — convert events to agent memories

    Extension subsystems (economy, social, health) insert their stages
    into this pipeline without modifying this function.
    """
    from app.simulation.stages.world_advance import advance_world
    from app.simulation.stages.agent_refresh import refresh_agents
    from app.simulation.stages.opportunity_gen import generate_opportunities
    from app.simulation.stages.action_resolve import resolve_actions
    from app.simulation.stages.event_hooks import create_turn_events
    from app.simulation.stages.memory_hooks import record_memories

    pipeline = TurnPipeline()
    pipeline.append("advance_world", advance_world)
    pipeline.append("refresh_agents", refresh_agents)
    pipeline.append("generate_opportunities", generate_opportunities)
    pipeline.append("resolve_actions", resolve_actions)
    pipeline.append("create_turn_events", create_turn_events)
    pipeline.append("record_memories", record_memories)
    return pipeline
