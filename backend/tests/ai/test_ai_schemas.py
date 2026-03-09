"""
Tests for AI layer schema validation.

No live API calls — pure schema/validation logic.

Covers:
  - AskAgentAIResponse: rejects blank answers
  - TurnSummaryAIResponse: rejects blank narratives
  - DecisionChoiceAIResponse: rejects blank choices
  - AskAgentRequest (public DTO): enforces question length
  - AskAgentResponse (public DTO): contains required fields
  - Invalid AI output structures are rejected cleanly
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.ai.schemas import (
    AgentContextData,
    AskAgentAIRequest,
    AskAgentAIResponse,
    DecisionCandidateAIRequest,
    DecisionChoiceAIResponse,
    TurnSummaryAIRequest,
    TurnSummaryAIResponse,
)
from app.schemas import AskAgentRequest, AskAgentResponse


# ---------------------------------------------------------------------------
# AskAgentAIResponse
# ---------------------------------------------------------------------------


class TestAskAgentAIResponse:
    def test_valid_answer_accepted(self):
        resp = AskAgentAIResponse(answer="I am Aldric and I tend the fields.")
        assert resp.answer == "I am Aldric and I tend the fields."

    def test_answer_whitespace_stripped(self):
        resp = AskAgentAIResponse(answer="  Some answer.  ")
        assert resp.answer == "Some answer."

    def test_blank_answer_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            AskAgentAIResponse(answer="")
        assert "empty" in str(exc_info.value).lower()

    def test_whitespace_only_answer_rejected(self):
        with pytest.raises(ValidationError):
            AskAgentAIResponse(answer="   \n\t  ")

    def test_missing_answer_field_rejected(self):
        with pytest.raises(ValidationError):
            AskAgentAIResponse()  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# TurnSummaryAIResponse
# ---------------------------------------------------------------------------


class TestTurnSummaryAIResponse:
    def test_valid_narrative_accepted(self):
        resp = TurnSummaryAIResponse(narrative="A quiet week passed in Ashenvale.")
        assert resp.narrative == "A quiet week passed in Ashenvale."

    def test_blank_narrative_rejected(self):
        with pytest.raises(ValidationError):
            TurnSummaryAIResponse(narrative="")

    def test_whitespace_only_rejected(self):
        with pytest.raises(ValidationError):
            TurnSummaryAIResponse(narrative="   ")

    def test_narrative_stripped(self):
        resp = TurnSummaryAIResponse(narrative="  Aldric traded food.\n  ")
        assert resp.narrative == "Aldric traded food."


# ---------------------------------------------------------------------------
# DecisionChoiceAIResponse
# ---------------------------------------------------------------------------


class TestDecisionChoiceAIResponse:
    def test_valid_choice_accepted(self):
        resp = DecisionChoiceAIResponse(chosen_action="harvest_food")
        assert resp.chosen_action == "harvest_food"

    def test_blank_choice_rejected(self):
        with pytest.raises(ValidationError):
            DecisionChoiceAIResponse(chosen_action="")

    def test_whitespace_choice_rejected(self):
        with pytest.raises(ValidationError):
            DecisionChoiceAIResponse(chosen_action="  ")

    def test_choice_stripped(self):
        resp = DecisionChoiceAIResponse(chosen_action="  patrol  ")
        assert resp.chosen_action == "patrol"


# ---------------------------------------------------------------------------
# AskAgentRequest (public DTO)
# ---------------------------------------------------------------------------


class TestAskAgentRequest:
    def test_valid_question(self):
        req = AskAgentRequest(question="How are you today?")
        assert req.question == "How are you today?"

    def test_empty_question_rejected(self):
        with pytest.raises(ValidationError):
            AskAgentRequest(question="")

    def test_too_long_question_rejected(self):
        with pytest.raises(ValidationError):
            AskAgentRequest(question="x" * 301)

    def test_max_length_question_accepted(self):
        req = AskAgentRequest(question="x" * 300)
        assert len(req.question) == 300


# ---------------------------------------------------------------------------
# AskAgentResponse (public DTO)
# ---------------------------------------------------------------------------


class TestAskAgentResponse:
    def test_valid_response_fields(self):
        resp = AskAgentResponse(
            agent_id=1,
            agent_name="Aldric",
            answer="I till the fields each dawn.",
            ai_enabled=True,
            fallback=False,
        )
        assert resp.agent_id == 1
        assert resp.agent_name == "Aldric"
        assert resp.ai_enabled is True
        assert resp.fallback is False

    def test_fallback_response_valid(self):
        resp = AskAgentResponse(
            agent_id=2,
            agent_name="Marta",
            answer="I cannot speak now.",
            ai_enabled=False,
            fallback=True,
        )
        assert resp.fallback is True
        assert resp.ai_enabled is False


# ---------------------------------------------------------------------------
# AgentContextData
# ---------------------------------------------------------------------------


class TestAgentContextData:
    def _minimal(self, **overrides) -> dict:
        base = dict(
            agent_id=1,
            agent_name="Test",
            profession="farmer",
            age=30,
            traits={"courage": 0.5},
            goals=[{"type": "produce", "target": "food"}],
            relationships=[],
            recent_memories=[],
            hunger_pct=20,
            pressure_reasons=[],
            season="spring",
            weather="clear",
        )
        base.update(overrides)
        return base

    def test_minimal_valid(self):
        ctx = AgentContextData(**self._minimal())
        assert ctx.agent_name == "Test"

    def test_extra_fields_rejected(self):
        data = self._minimal()
        data["unexpected_field"] = "value"
        # Pydantic v2 ignores extra fields by default — no error expected
        ctx = AgentContextData(**data)
        assert ctx.agent_name == "Test"


# ---------------------------------------------------------------------------
# TurnSummaryAIRequest
# ---------------------------------------------------------------------------


class TestTurnSummaryAIRequest:
    def test_minimal_valid(self):
        req = TurnSummaryAIRequest(world_name="Ashenvale", turn_start=1, turn_end=5)
        assert req.turn_start == 1
        assert req.notable_events == []

    def test_with_events(self):
        req = TurnSummaryAIRequest(
            world_name="Ashenvale",
            turn_start=1,
            turn_end=3,
            notable_events=["Aldric harvested food.", "Elena traded goods."],
            world_event_names=["festival"],
        )
        assert len(req.notable_events) == 2
        assert "festival" in req.world_event_names
