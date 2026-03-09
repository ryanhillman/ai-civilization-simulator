"""
Typed request/response schemas for all AI service interactions.

These are INTERNAL to the AI layer — they are never exposed directly in
public API responses. Public DTOs live in app.schemas.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Shared agent context (compact, serializable)
# ---------------------------------------------------------------------------


class AgentContextData(BaseModel):
    """
    Compact, serializable snapshot of an agent + world for LLM prompt building.

    Built by context_builder; consumed by AIService prompt formatters.
    Never included verbatim in public API responses.
    """

    agent_id: int
    agent_name: str
    profession: str
    age: int
    traits: dict[str, float]
    goals: list[dict[str, Any]]
    relationships: list[dict[str, Any]]  # [{name, status, trust, warmth}]
    recent_memories: list[str]           # last 5 memory summaries
    hunger_pct: int                      # 0-100
    pressure_reasons: list[str]
    season: str
    weather: str
    world_name: str = "the village"
    is_alive: bool = True                # False for deceased agents


# ---------------------------------------------------------------------------
# Ask-agent
# ---------------------------------------------------------------------------


class AskAgentAIRequest(BaseModel):
    """Internal request to the AI service for an in-character agent answer."""

    context: AgentContextData
    question: str = Field(max_length=300)


class AskAgentAIResponse(BaseModel):
    """Validated AI response for ask-agent. Rejected if answer is blank."""

    answer: str

    @field_validator("answer")
    @classmethod
    def answer_nonempty(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("AI answer cannot be empty")
        return stripped


# ---------------------------------------------------------------------------
# Turn narrative summary
# ---------------------------------------------------------------------------


class TurnSummaryAIRequest(BaseModel):
    """Internal request to the AI service for a narrative run summary."""

    world_name: str
    turn_start: int
    turn_end: int
    notable_events: list[str] = Field(default_factory=list)   # max 15 used
    world_event_names: list[str] = Field(default_factory=list)


class TurnSummaryAIResponse(BaseModel):
    """Validated AI response for narrative summary. Rejected if blank."""

    narrative: str

    @field_validator("narrative")
    @classmethod
    def narrative_nonempty(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Narrative cannot be empty")
        return stripped


# ---------------------------------------------------------------------------
# Decision support
# ---------------------------------------------------------------------------


class DecisionCandidateAIRequest(BaseModel):
    """Internal request for AI decision support (action tie-breaking)."""

    context: AgentContextData
    candidates: list[str]  # valid action_type strings from the deterministic engine


class DecisionChoiceAIResponse(BaseModel):
    """Validated AI response for decision support."""

    chosen_action: str

    @field_validator("chosen_action")
    @classmethod
    def choice_nonempty(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Chosen action cannot be empty")
        return stripped
