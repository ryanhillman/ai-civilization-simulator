"""
TurnPipeline

An ordered, named list of stage functions. Each stage has the signature:

    (TurnContext) -> TurnContext

Stages are applied in sequence; the output context of each stage becomes
the input of the next. This makes the pipeline easy to test in isolation
(call any stage directly) and easy to extend (insert_after / append).

Usage:

    pipeline = build_default_pipeline()   # Phase 2 — 6 stages
    pipeline = build_phase3_pipeline()    # Phase 3 — 10 stages
    ctx_out = pipeline.run(ctx_in)

Phase 3 stages vs Phase 2
--------------------------
Phase 3 inserts four new stages around the existing six:

  apply_world_events   — before refresh_agents: festivals, storms, outbreaks
  compute_pressure     — after  refresh_agents: deterministic pressure profiles
  economy_opportunities— after  generate_opportunities: inter-agent food trade
  update_relationships — after  resolve_actions: trust/warmth/resentment deltas
  spread_gossip        — after  update_relationships: rumor creation + propagation

build_default_pipeline() intentionally stays at 6 stages so Phase 2 tests
remain valid. build_phase3_pipeline() is the live production pipeline.
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
# Phase 2 default pipeline (preserved — 6 stages, exact names)
# ---------------------------------------------------------------------------


def build_default_pipeline() -> TurnPipeline:
    """
    Build the canonical Phase 2 turn pipeline with six core stages.

    Stage order:
      1. advance_world        — tick day, season, weather
      2. refresh_agents       — hunger, starvation check
      3. generate_opportunities — build action candidate list
      4. resolve_actions      — select + apply best action per agent
      5. create_turn_events   — convert actions to timeline events
      6. record_memories      — convert events to agent memories

    This function is intentionally frozen at 6 stages so Phase 2 tests
    remain valid. Use build_phase3_pipeline() for the live simulation.
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


# ---------------------------------------------------------------------------
# Phase 3 pipeline — economy, social, pressure, world events (10 stages)
# ---------------------------------------------------------------------------


def build_phase3_pipeline() -> TurnPipeline:
    """
    Build the Phase 3 turn pipeline.

    Stage order:
      1.  advance_world         — tick day, season, weather
      2.  apply_world_events    — festivals, poor harvest, storms, sickness outbreaks
      3.  refresh_agents        — hunger consumption, starvation check
      4.  compute_pressure      — deterministic per-agent pressure scores
      5.  generate_opportunities — profession actions (pressure-scored, event-modified)
      6.  economy_opportunities  — inter-agent food trade (pressure-priced)
      7.  resolve_actions        — select + apply best action (pressure-aware)
      8.  update_relationships   — trust/warmth/resentment deltas from interactions
      9.  spread_gossip          — rumor creation and propagation
      10. create_turn_events     — convert actions to timeline events
      11. record_memories        — convert events to agent memories
    """
    from app.simulation.stages.world_advance import advance_world
    from app.simulation.stages.world_events import apply_world_events
    from app.simulation.stages.agent_refresh import refresh_agents
    from app.simulation.stages.compute_pressure import compute_pressure_stage
    from app.simulation.stages.opportunity_gen import generate_opportunities
    from app.simulation.economy import generate_economy_opportunities
    from app.simulation.stages.action_resolve import resolve_actions
    from app.simulation.social import update_relationships, spread_gossip
    from app.simulation.stages.event_hooks import create_turn_events
    from app.simulation.stages.memory_hooks import record_memories

    pipeline = TurnPipeline()
    pipeline.append("advance_world", advance_world)
    pipeline.append("apply_world_events", apply_world_events)
    pipeline.append("refresh_agents", refresh_agents)
    pipeline.append("compute_pressure", compute_pressure_stage)
    pipeline.append("generate_opportunities", generate_opportunities)
    pipeline.append("economy_opportunities", generate_economy_opportunities)
    pipeline.append("resolve_actions", resolve_actions)
    pipeline.append("update_relationships", update_relationships)
    pipeline.append("spread_gossip", spread_gossip)
    pipeline.append("create_turn_events", create_turn_events)
    pipeline.append("record_memories", record_memories)
    return pipeline
