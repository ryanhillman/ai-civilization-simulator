"""
AIService — selective LLM interpretation layer.

Architecture rules enforced here:
  - AI never mutates world state directly
  - AI only selects from a validated candidate action list (decision support)
  - All methods degrade gracefully: None / empty dict on any failure
  - ai_enabled=False short-circuits before any network call

The module-level `ai_service` singleton is the standard injection point.
Pass a mock client in tests to avoid live API calls.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from app.ai.schemas import (
    AgentContextData,
    AskAgentAIResponse,
    TurnSummaryAIRequest,
    TurnSummaryAIResponse,
)

if TYPE_CHECKING:
    from app.simulation.types import TurnContext

logger = logging.getLogger(__name__)

_PROMPT_DIR = Path(__file__).parent / "prompts"


def _load_prompt(name: str) -> str:
    return (_PROMPT_DIR / name).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Prompt formatting helpers
# ---------------------------------------------------------------------------


def _format_agent_vars(ctx: AgentContextData) -> dict[str, str]:
    """Produce the substitution variables for agent-focused prompts."""
    traits_text = (
        ", ".join(f"{k}={v:.1f}" for k, v in ctx.traits.items()) or "unknown"
    )
    goals_text = (
        ", ".join(
            f"{g.get('type', '?')} {g.get('target', '')}".strip()
            for g in ctx.goals
        )
        or "none"
    )
    if ctx.relationships:
        rels_text = "; ".join(
            f"{r['name']} ({r['status']}, trust={r['trust']})"
            for r in ctx.relationships
        )
    else:
        rels_text = "no notable relationships"
    memories_text = (
        "; ".join(ctx.recent_memories) if ctx.recent_memories else "none"
    )
    pressure_note = (
        f"; pressures: {', '.join(ctx.pressure_reasons)}"
        if ctx.pressure_reasons
        else ""
    )
    return {
        "traits_text": traits_text,
        "goals_text": goals_text,
        "rels_text": rels_text,
        "memories_text": memories_text,
        "pressure_note": pressure_note,
    }


# ---------------------------------------------------------------------------
# Meaningful-ambiguity detection (decision support)
# ---------------------------------------------------------------------------


def _find_ambiguous_agents(
    ctx: "TurnContext",
    threshold: float = 0.15,
) -> dict[int, list[str]]:
    """
    Return agents where the top two opportunity scores differ by <= threshold.

    These are the only agents for whom AI decision support fires. If the
    deterministic pressure system has produced a clear winner (score diff >
    threshold), AI is not called — no ambiguity, no cost.
    """
    ambiguous: dict[int, list[str]] = {}
    for agent in ctx.world_state.living_agents:
        agent_opps = [o for o in ctx.opportunities if o.agent_id == agent.id]
        if len(agent_opps) < 2:
            continue
        sorted_opps = sorted(agent_opps, key=lambda o: o.score, reverse=True)
        top_score = sorted_opps[0].score
        if abs(top_score - sorted_opps[1].score) <= threshold:
            candidates = [
                o.action_type
                for o in sorted_opps
                if abs(top_score - o.score) <= threshold
            ]
            # Deduplicate while preserving order
            seen: set[str] = set()
            deduped: list[str] = []
            for c in candidates:
                if c not in seen:
                    seen.add(c)
                    deduped.append(c)
            ambiguous[agent.id] = deduped
    return ambiguous


# ---------------------------------------------------------------------------
# AIService
# ---------------------------------------------------------------------------


class AIService:
    """
    Selective AI interpretation service.

    Accepts an optional pre-configured client for testing (dependency
    injection). If client=None, initializes lazily from settings on first
    real call.
    """

    def __init__(self, client=None) -> None:
        self._client = client
        self._ask_agent_prompt = _load_prompt("ask_agent.txt")
        self._turn_summary_prompt = _load_prompt("turn_summary.txt")

    # ------------------------------------------------------------------
    # Client lifecycle
    # ------------------------------------------------------------------

    def _get_client(self):
        """Return the Anthropic async client, or None if AI is unavailable."""
        if self._client is not None:
            return self._client

        from app.core.config import settings

        if not settings.ai_enabled:
            return None
        if not settings.anthropic_api_key:
            logger.warning("AI enabled but ANTHROPIC_API_KEY is not set")
            return None
        try:
            import anthropic

            return anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        except Exception as exc:
            logger.warning("Failed to initialize Anthropic client: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Public: ask-agent
    # ------------------------------------------------------------------

    async def ask_agent(
        self,
        context: AgentContextData,
        question: str,
    ) -> Optional[AskAgentAIResponse]:
        """
        Return an in-character answer from the agent, or None on failure/disabled.

        Never raises. All errors degrade to None so the route can return a
        polite fallback.
        """
        from app.core.config import settings

        if not settings.ai_enabled or not settings.ai_ask_agent_enabled:
            return None

        client = self._get_client()
        if client is None:
            return None

        fmt = _format_agent_vars(context)
        prompt = self._ask_agent_prompt.format(
            agent_name=context.agent_name,
            profession=context.profession,
            age=context.age,
            world_name=context.world_name,
            question=question,
            hunger_pct=context.hunger_pct,
            season=context.season,
            weather=context.weather,
            **fmt,
        )

        try:
            resp = await client.messages.create(
                model=settings.ai_model,
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}],
            )
            text = resp.content[0].text
            return AskAgentAIResponse(answer=text)
        except Exception as exc:
            logger.warning("ask_agent AI call failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Public: turn narrative summary
    # ------------------------------------------------------------------

    async def generate_turn_summary(
        self,
        request: TurnSummaryAIRequest,
    ) -> Optional[TurnSummaryAIResponse]:
        """
        Generate a narrative summary for a multi-turn run, or None on failure.

        Only called when n > 1 turns ran. Single-turn 'next' uses the
        deterministic summary from the runner.
        """
        from app.core.config import settings

        if not settings.ai_enabled or not settings.ai_summary_enabled:
            return None

        client = self._get_client()
        if client is None:
            return None

        events_text = "\n".join(f"- {e}" for e in request.notable_events[:15])
        if request.world_event_names:
            events_text += f"\nWorld events: {', '.join(request.world_event_names)}"
        if not events_text:
            events_text = "No notable events recorded."

        prompt = self._turn_summary_prompt.format(
            world_name=request.world_name,
            turn_start=request.turn_start,
            turn_end=request.turn_end,
            events_text=events_text,
        )

        try:
            resp = await client.messages.create(
                model=settings.ai_model,
                max_tokens=150,
                messages=[{"role": "user", "content": prompt}],
            )
            text = resp.content[0].text
            return TurnSummaryAIResponse(narrative=text)
        except Exception as exc:
            logger.warning("generate_turn_summary AI call failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Public: decision support
    # ------------------------------------------------------------------

    async def advise_decisions(
        self,
        ctx: "TurnContext",
        name_map: dict[int, str],
    ) -> dict[int, str]:
        """
        Return AI-selected action types for meaningfully ambiguous agents.

        Returns empty dict if AI is disabled, no ambiguity found, or any
        failure occurs. The engine always validates the returned choice
        against the actual candidate list before using it.
        """
        from app.core.config import settings

        if not settings.ai_enabled:
            return {}

        client = self._get_client()
        if client is None:
            return {}

        ambiguous = _find_ambiguous_agents(ctx)
        if not ambiguous:
            return {}

        from app.ai.context_builder import build_agent_context_from_state

        hints: dict[int, str] = {}
        calls = 0
        for agent_id, candidates in ambiguous.items():
            if calls >= settings.ai_max_calls_per_run:
                break
            agent = ctx.world_state.agent_by_id(agent_id)
            if agent is None:
                continue
            context = build_agent_context_from_state(agent, ctx.world_state, name_map)
            chosen = await self._choose_action(client, settings.ai_model, context, candidates)
            # Strict validation: chosen must be in the candidate list
            if chosen and chosen in candidates:
                hints[agent_id] = chosen
            calls += 1

        return hints

    async def _choose_action(
        self,
        client,
        model: str,
        context: AgentContextData,
        candidates: list[str],
    ) -> Optional[str]:
        """Ask AI to pick one action from a bounded candidate list."""
        candidates_text = "\n".join(f"- {c}" for c in candidates)
        fmt = _format_agent_vars(context)
        prompt = (
            f"You are {context.agent_name}, a {context.profession} in a medieval village.\n\n"
            f"Situation: hunger={context.hunger_pct}%, season={context.season}, "
            f"weather={context.weather}"
            + (
                f", pressures: {', '.join(context.pressure_reasons)}"
                if context.pressure_reasons
                else ""
            )
            + f"\nTraits: {fmt['traits_text']}"
            + (
                f"\nRecent: {fmt['memories_text']}"
                if context.recent_memories
                else ""
            )
            + f"\n\nChoose ONE action from this list:\n{candidates_text}"
            + "\n\nReply with ONLY the exact action name, nothing else."
        )

        try:
            resp = await client.messages.create(
                model=model,
                max_tokens=30,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = (
                resp.content[0].text.strip().lower().replace(" ", "_").replace("-", "_")
            )
            # Exact match
            if raw in candidates:
                return raw
            # Substring fallback (handles minor whitespace / extra words)
            for c in candidates:
                if c in raw:
                    return c
            logger.debug(
                "AI chose %r which is not in candidates %s", raw, candidates
            )
            return None
        except Exception as exc:
            logger.warning("_choose_action AI call failed: %s", exc)
            return None


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

# Default instance — override _client in tests for mock injection:
#   from app.ai.service import ai_service
#   ai_service._client = mock_anthropic_client
ai_service = AIService()
