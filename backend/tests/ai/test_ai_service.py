"""
Tests for AIService logic and fallback behavior.

All tests use a mock Azure OpenAI client — no live API calls.

Covers:
  - ask_agent: returns answer when AI responds correctly
  - ask_agent: returns None when AI is disabled
  - ask_agent: returns None when client raises
  - ask_agent: returns None when AI returns blank text
  - generate_turn_summary: returns narrative when AI responds
  - generate_turn_summary: returns None when disabled
  - generate_turn_summary: returns None on client error
  - advise_decisions: returns empty dict when disabled
  - advise_decisions: only returns actions in the candidate list (validation)
  - _find_ambiguous_agents: correctly identifies close-score pairs
  - Decision support fallback: deterministic pipeline runs when hints fail
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ai.schemas import AgentContextData, TurnSummaryAIRequest
from app.ai.service import AIService, _find_ambiguous_agents


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_mock_client(text: str) -> MagicMock:
    """Return a mock Azure OpenAI client that always returns the given text."""
    mock_message = SimpleNamespace(content=text)
    mock_choice = SimpleNamespace(message=mock_message)
    mock_response = SimpleNamespace(choices=[mock_choice])
    client = MagicMock()
    client.chat = MagicMock()
    client.chat.completions = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=mock_response)
    return client


def _make_error_client() -> MagicMock:
    """Return a mock client whose create() always raises."""
    client = MagicMock()
    client.chat = MagicMock()
    client.chat.completions = MagicMock()
    client.chat.completions.create = AsyncMock(side_effect=RuntimeError("API error"))
    return client


def _minimal_context(**overrides) -> AgentContextData:
    base = dict(
        agent_id=1,
        agent_name="Aldric",
        profession="farmer",
        age=42,
        traits={"courage": 0.4, "warmth": 0.8},
        goals=[{"type": "produce", "target": "food"}],
        relationships=[],
        recent_memories=["Harvested grain last turn."],
        hunger_pct=20,
        pressure_reasons=[],
        season="spring",
        weather="clear",
        world_name="Ashenvale",
    )
    base.update(overrides)
    return AgentContextData(**base)


# ---------------------------------------------------------------------------
# ask_agent
# ---------------------------------------------------------------------------


class TestAskAgent:
    @pytest.mark.asyncio
    async def test_returns_answer_when_ai_responds(self):
        svc = AIService(client=_make_mock_client("I tend the fields at dawn."))
        with patch("app.core.config.settings") as mock_settings:
            mock_settings.ai_enabled = True
            mock_settings.ai_ask_agent_enabled = True
            mock_settings.azure_openai_deployment_name = "test-deployment"
            ctx = _minimal_context()
            result = await svc.ask_agent(ctx, "What do you do each morning?")

        assert result is not None
        assert result.answer == "I tend the fields at dawn."

    @pytest.mark.asyncio
    async def test_returns_none_when_ai_disabled(self):
        svc = AIService(client=_make_mock_client("Should not be called"))
        with patch("app.core.config.settings") as mock_settings:
            mock_settings.ai_enabled = False
            mock_settings.ai_ask_agent_enabled = True
            result = await svc.ask_agent(_minimal_context(), "Hello?")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_ask_agent_feature_disabled(self):
        svc = AIService(client=_make_mock_client("Should not be called"))
        with patch("app.core.config.settings") as mock_settings:
            mock_settings.ai_enabled = True
            mock_settings.ai_ask_agent_enabled = False
            result = await svc.ask_agent(_minimal_context(), "Hello?")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_client_raises(self):
        svc = AIService(client=_make_error_client())
        with patch("app.core.config.settings") as mock_settings:
            mock_settings.ai_enabled = True
            mock_settings.ai_ask_agent_enabled = True
            mock_settings.azure_openai_deployment_name = "test-deployment"
            result = await svc.ask_agent(_minimal_context(), "Hello?")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_ai_returns_blank(self):
        svc = AIService(client=_make_mock_client("   "))
        with patch("app.core.config.settings") as mock_settings:
            mock_settings.ai_enabled = True
            mock_settings.ai_ask_agent_enabled = True
            mock_settings.azure_openai_deployment_name = "test-deployment"
            result = await svc.ask_agent(_minimal_context(), "Hello?")

        # Blank text → AskAgentAIResponse validation fails → None
        assert result is None

    @pytest.mark.asyncio
    async def test_answer_is_stripped(self):
        svc = AIService(client=_make_mock_client("\n  A fine morning.  \n"))
        with patch("app.core.config.settings") as mock_settings:
            mock_settings.ai_enabled = True
            mock_settings.ai_ask_agent_enabled = True
            mock_settings.azure_openai_deployment_name = "test-deployment"
            result = await svc.ask_agent(_minimal_context(), "Morning?")

        assert result is not None
        assert result.answer == "A fine morning."


# ---------------------------------------------------------------------------
# generate_turn_summary
# ---------------------------------------------------------------------------


class TestGenerateTurnSummary:
    @pytest.mark.asyncio
    async def test_returns_narrative_when_ai_responds(self):
        svc = AIService(client=_make_mock_client("Elena traded grain while Roland patrolled."))
        request = TurnSummaryAIRequest(
            world_name="Ashenvale",
            turn_start=1,
            turn_end=5,
            notable_events=["Elena traded goods.", "Roland patrolled."],
        )
        with patch("app.core.config.settings") as mock_settings:
            mock_settings.ai_enabled = True
            mock_settings.ai_summary_enabled = True
            mock_settings.azure_openai_deployment_name = "test-deployment"
            result = await svc.generate_turn_summary(request)

        assert result is not None
        assert "Elena" in result.narrative

    @pytest.mark.asyncio
    async def test_returns_none_when_ai_disabled(self):
        svc = AIService(client=_make_mock_client("Ignored"))
        request = TurnSummaryAIRequest(world_name="A", turn_start=1, turn_end=3)
        with patch("app.core.config.settings") as mock_settings:
            mock_settings.ai_enabled = False
            mock_settings.ai_summary_enabled = True
            result = await svc.generate_turn_summary(request)

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_summary_disabled(self):
        svc = AIService(client=_make_mock_client("Ignored"))
        request = TurnSummaryAIRequest(world_name="A", turn_start=1, turn_end=3)
        with patch("app.core.config.settings") as mock_settings:
            mock_settings.ai_enabled = True
            mock_settings.ai_summary_enabled = False
            result = await svc.generate_turn_summary(request)

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_client_error(self):
        svc = AIService(client=_make_error_client())
        request = TurnSummaryAIRequest(world_name="A", turn_start=1, turn_end=3)
        with patch("app.core.config.settings") as mock_settings:
            mock_settings.ai_enabled = True
            mock_settings.ai_summary_enabled = True
            mock_settings.azure_openai_deployment_name = "test-deployment"
            result = await svc.generate_turn_summary(request)

        assert result is None


# ---------------------------------------------------------------------------
# advise_decisions
# ---------------------------------------------------------------------------


class TestAdviseDecisions:
    def _make_ctx_with_opps(self, opps_by_agent: dict[int, list[tuple[str, float]]]):
        """Build a minimal TurnContext with specific opportunity scores."""
        from app.simulation.types import Opportunity, TurnContext, WorldState
        from app.enums import Season

        opportunities = []
        agent_ids = list(opps_by_agent.keys())
        for agent_id, action_scores in opps_by_agent.items():
            for action_type, score in action_scores:
                opportunities.append(
                    Opportunity(agent_id=agent_id, action_type=action_type, score=score)
                )

        # Minimal world with live agents
        agents = []
        for aid in agent_ids:
            from app.simulation.types import AgentState
            from app.enums import Profession
            agents.append(
                AgentState(
                    id=aid,
                    world_id=1,
                    name=f"Agent{aid}",
                    profession=Profession.farmer,
                    age=30,
                )
            )

        ws = WorldState(
            id=1, name="Test", current_turn=1, current_day=1,
            current_season=Season.spring, weather="clear", agents=agents,
        )
        return TurnContext(world_state=ws, opportunities=opportunities)

    @pytest.mark.asyncio
    async def test_returns_empty_when_ai_disabled(self):
        svc = AIService(client=_make_mock_client("harvest_food"))
        ctx = self._make_ctx_with_opps({1: [("harvest_food", 1.0), ("rest", 0.95)]})
        with patch("app.core.config.settings") as mock_settings:
            mock_settings.ai_enabled = False
            result = await svc.advise_decisions(ctx, {1: "Agent1"})

        assert result == {}

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_ambiguity(self):
        # Score gap of 0.5 > threshold 0.15 → not ambiguous
        svc = AIService(client=_make_mock_client("harvest_food"))
        ctx = self._make_ctx_with_opps({1: [("harvest_food", 1.5), ("rest", 1.0)]})
        with patch("app.core.config.settings") as mock_settings:
            mock_settings.ai_enabled = True
            mock_settings.ai_max_calls_per_run = 3
            result = await svc.advise_decisions(ctx, {1: "Agent1"})

        assert result == {}

    @pytest.mark.asyncio
    async def test_returns_valid_candidate_when_ambiguous(self):
        svc = AIService(client=_make_mock_client("harvest_food"))
        # Score gap of 0.05 <= threshold → ambiguous
        ctx = self._make_ctx_with_opps(
            {1: [("harvest_food", 1.0), ("rest", 0.97)]}
        )
        with patch("app.core.config.settings") as mock_settings:
            mock_settings.ai_enabled = True
            mock_settings.ai_max_calls_per_run = 3
            mock_settings.azure_openai_deployment_name = "test-deployment"
            result = await svc.advise_decisions(ctx, {1: "Agent1"})

        # AI returned "harvest_food" which is a valid candidate
        assert result.get(1) == "harvest_food"

    @pytest.mark.asyncio
    async def test_invalid_ai_choice_not_applied(self):
        # AI returns an action not in the candidate list
        svc = AIService(client=_make_mock_client("steal_food"))
        ctx = self._make_ctx_with_opps(
            {1: [("harvest_food", 1.0), ("rest", 0.97)]}
        )
        with patch("app.core.config.settings") as mock_settings:
            mock_settings.ai_enabled = True
            mock_settings.ai_max_calls_per_run = 3
            mock_settings.azure_openai_deployment_name = "test-deployment"
            result = await svc.advise_decisions(ctx, {1: "Agent1"})

        # "steal_food" is NOT in the candidate list → not applied
        assert 1 not in result

    @pytest.mark.asyncio
    async def test_returns_empty_on_client_error(self):
        svc = AIService(client=_make_error_client())
        ctx = self._make_ctx_with_opps(
            {1: [("harvest_food", 1.0), ("rest", 0.97)]}
        )
        with patch("app.core.config.settings") as mock_settings:
            mock_settings.ai_enabled = True
            mock_settings.ai_max_calls_per_run = 3
            mock_settings.azure_openai_deployment_name = "test-deployment"
            result = await svc.advise_decisions(ctx, {1: "Agent1"})

        assert result == {}


# ---------------------------------------------------------------------------
# _find_ambiguous_agents (pure logic, no AI)
# ---------------------------------------------------------------------------


class TestFindAmbiguousAgents:
    def _make_ctx(self, opps_by_agent: dict[int, list[tuple[str, float]]]):
        from app.simulation.types import Opportunity, TurnContext, WorldState, AgentState
        from app.enums import Season, Profession

        opportunities = []
        agents = []
        for agent_id, action_scores in opps_by_agent.items():
            for action_type, score in action_scores:
                opportunities.append(
                    Opportunity(agent_id=agent_id, action_type=action_type, score=score)
                )
            agents.append(
                AgentState(
                    id=agent_id, world_id=1, name=f"A{agent_id}",
                    profession=Profession.farmer, age=30,
                )
            )
        ws = WorldState(
            id=1, name="T", current_turn=1, current_day=1,
            current_season=Season.spring, weather="clear", agents=agents,
        )
        return TurnContext(world_state=ws, opportunities=opportunities)

    def test_close_scores_are_ambiguous(self):
        ctx = self._make_ctx({1: [("harvest_food", 1.0), ("rest", 0.90)]})
        result = _find_ambiguous_agents(ctx, threshold=0.15)
        assert 1 in result
        assert set(result[1]) == {"harvest_food", "rest"}

    def test_wide_score_gap_not_ambiguous(self):
        ctx = self._make_ctx({1: [("harvest_food", 2.0), ("rest", 1.0)]})
        result = _find_ambiguous_agents(ctx, threshold=0.15)
        assert 1 not in result

    def test_single_opportunity_not_ambiguous(self):
        ctx = self._make_ctx({1: [("rest", 1.0)]})
        result = _find_ambiguous_agents(ctx, threshold=0.15)
        assert 1 not in result

    def test_multiple_agents_mixed_ambiguity(self):
        ctx = self._make_ctx({
            1: [("harvest_food", 1.0), ("rest", 0.95)],  # ambiguous
            2: [("craft_tools", 2.0), ("rest", 1.0)],    # clear winner
        })
        result = _find_ambiguous_agents(ctx, threshold=0.15)
        assert 1 in result
        assert 2 not in result

    def test_candidates_deduplicated(self):
        ctx = self._make_ctx({
            1: [("harvest_food", 1.0), ("harvest_food", 1.0), ("rest", 0.92)],
        })
        result = _find_ambiguous_agents(ctx, threshold=0.15)
        if 1 in result:
            assert len(result[1]) == len(set(result[1]))


# ---------------------------------------------------------------------------
# Pre-selected action validation in resolve_actions
# ---------------------------------------------------------------------------


class TestPreSelectedActionValidation:
    """
    Ensures that resolve_actions respects pre_selected_actions only for
    valid (in-candidate-list) action types, and falls back deterministically
    otherwise.
    """

    def _run_with_hint(self, action_type: str, valid: bool):
        from app.enums import Profession
        from app.simulation.types import Opportunity, TurnContext, WorldState, AgentState
        from app.enums import Season
        from app.simulation.stages.action_resolve import resolve_actions

        agent = AgentState(
            id=1, world_id=1, name="Test",
            profession=Profession.farmer, age=30,
            goals=[{"type": "produce", "priority": 1}],
            personality_traits={"warmth": 0.5, "courage": 0.5,
                                 "greed": 0.2, "cunning": 0.3, "piety": 0.4},
        )
        ws = WorldState(
            id=1, name="T", current_turn=1, current_day=1,
            current_season=Season.spring, weather="clear", agents=[agent],
        )
        opps = [
            Opportunity(agent_id=1, action_type="harvest_food", score=1.0),
            Opportunity(agent_id=1, action_type="rest", score=0.5),
        ]
        ctx = TurnContext(
            world_state=ws,
            opportunities=opps,
            pre_selected_actions={1: action_type} if valid else {1: "nonexistent_action"},
        )
        result_ctx = resolve_actions(ctx)
        return result_ctx.resolved_actions[0].action_type

    def test_valid_hint_is_used(self):
        action = self._run_with_hint("rest", valid=True)
        assert action == "rest"

    def test_invalid_hint_falls_back_to_deterministic(self):
        # "nonexistent_action" is not in the opportunity list → fallback
        action = self._run_with_hint("nonexistent_action", valid=False)
        # Deterministic fallback: goal is "produce" → harvest_food
        assert action == "harvest_food"
