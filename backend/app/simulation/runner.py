"""
TurnRunner

Orchestrates one or more simulation turns.

The runner:
  1. Bumps current_turn on the WorldState.
  2. Wraps it in a TurnContext.
  3. Passes the context through the TurnPipeline.
  4. Packages the output into a TurnResult.

All persistence is the caller's responsibility. The runner has zero DB
or I/O dependencies and can be used directly in tests or from the
SimulationService in the domain layer.

One-turn:
    result = runner.run_turn(world)

Multi-turn (feeds each result's world_state back as the next input):
    results = runner.run_turns(world, n=10)
"""
from __future__ import annotations

from app.simulation.pipeline import TurnPipeline, build_default_pipeline
from app.simulation.types import TurnContext, TurnEventRecord, TurnResult, WorldState


def build_turn_summary(events: list[TurnEventRecord]) -> str:
    """
    Build a deterministic plain-text summary from the turn's event list.

    Rules (stable, testable, no LLM):
    - No events      → fixed quiet-turn message.
    - Up to 5 events → join their descriptions with a space.
    - > 5 events     → first 5 descriptions + "...and N more events." trailer.

    This function is intentionally at module level (not a private method) so
    it can be tested directly without constructing a full TurnContext.
    """
    if not events:
        return "A quiet turn passed in the village."
    parts = [e.description for e in events[:5]]
    if len(events) > 5:
        parts.append(f"...and {len(events) - 5} more events.")
    return " ".join(parts)


class TurnRunner:
    def __init__(self, pipeline: TurnPipeline | None = None) -> None:
        self._pipeline = pipeline or build_default_pipeline()

    @property
    def pipeline(self) -> TurnPipeline:
        return self._pipeline

    # ------------------------------------------------------------------
    # Single turn
    # ------------------------------------------------------------------

    def run_turn(self, world: WorldState) -> TurnResult:
        """
        Execute one turn.

        The input WorldState is not mutated; a fresh WorldState is returned
        inside the TurnResult.
        """
        # Bump turn counter before the pipeline starts
        world = world.model_copy(update={"current_turn": world.current_turn + 1})

        ctx = TurnContext(world_state=world)
        ctx = self._pipeline.run(ctx)

        summary = self._build_summary(ctx)

        return TurnResult(
            world_id=world.id,
            turn_number=world.current_turn,
            world_state=ctx.world_state,
            resolved_actions=ctx.resolved_actions,
            events=ctx.events,
            memories=ctx.memories,
            summary=summary,
        )

    # ------------------------------------------------------------------
    # Multi-turn
    # ------------------------------------------------------------------

    def run_turns(self, world: WorldState, n: int) -> list[TurnResult]:
        """
        Execute n consecutive turns.

        Each turn's output WorldState feeds into the next turn's input,
        creating a fully chained simulation sequence.
        """
        if n < 1:
            return []

        results: list[TurnResult] = []
        current = world
        for _ in range(n):
            result = self.run_turn(current)
            results.append(result)
            current = result.world_state
        return results

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _build_summary(ctx: TurnContext) -> str:
        return build_turn_summary(ctx.events)
