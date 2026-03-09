"""
Tests for the deterministic ask-agent fallback response.

No DB, no AI, no async — pure unit tests for _fallback_answer.

Covers:
  - Profession-specific openers differ across professions
  - Sick agent gets illness-specific detail
  - Very hungry agent gets hunger-specific detail
  - Sick + very hungry combined gets the highest-priority detail
  - Hungry (but not very hungry) mentions food
  - Agent with a grudge hints at the foe by name
  - Agent with a recent memory references it
  - Agent with an ally (no grudge/memory) mentions them
  - Agent with no notable context gets generic close
  - Output is always deterministic (same input → same output)
"""
from __future__ import annotations

import pytest

from app.ai.schemas import AgentContextData
from app.api.routes.ai import _deceased_response, _fallback_answer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ctx(**overrides) -> AgentContextData:
    base = dict(
        agent_id=1,
        agent_name="Aldric",
        profession="farmer",
        age=35,
        traits={"courage": 0.5},
        goals=[],
        relationships=[],
        recent_memories=[],
        hunger_pct=10,
        pressure_reasons=[],
        season="spring",
        weather="clear",
        world_name="Ashenvale",
    )
    base.update(overrides)
    return AgentContextData(**base)


# ---------------------------------------------------------------------------
# Profession variation
# ---------------------------------------------------------------------------


class TestProfessionVariation:
    def test_healer_differs_from_soldier(self):
        healer = _fallback_answer(_ctx(agent_name="Marta", profession="healer"))
        soldier = _fallback_answer(_ctx(agent_name="Roland", profession="soldier"))
        assert healer != soldier

    def test_farmer_differs_from_merchant(self):
        farmer = _fallback_answer(_ctx(agent_name="Aldric", profession="farmer"))
        merchant = _fallback_answer(_ctx(agent_name="Venn", profession="merchant"))
        assert farmer != merchant

    def test_healer_opener_in_response(self):
        answer = _fallback_answer(_ctx(agent_name="Marta", profession="healer"))
        # Known opener for healer profession
        assert "someone who needs my care" in answer

    def test_soldier_opener_in_response(self):
        answer = _fallback_answer(_ctx(agent_name="Roland", profession="soldier"))
        assert "keep watch" in answer

    def test_farmer_opener_in_response(self):
        answer = _fallback_answer(_ctx(agent_name="Aldric", profession="farmer"))
        assert "harvest" in answer

    def test_unknown_profession_uses_generic_opener(self):
        answer = _fallback_answer(_ctx(profession="alchemist"))
        assert "alchemist" in answer  # name + profession always present
        assert "I am Aldric" in answer

    def test_agent_name_always_present(self):
        for prof in ("farmer", "healer", "soldier", "merchant", "blacksmith"):
            answer = _fallback_answer(_ctx(agent_name="TestAgent", profession=prof))
            assert "TestAgent" in answer

    def test_profession_always_present(self):
        for prof in ("farmer", "healer", "soldier"):
            answer = _fallback_answer(_ctx(profession=prof))
            assert prof in answer


# ---------------------------------------------------------------------------
# Pressure states
# ---------------------------------------------------------------------------


class TestPressureStates:
    def test_sick_agent_mentions_illness(self):
        answer = _fallback_answer(_ctx(pressure_reasons=["ill"]))
        assert "not well" in answer or "ill" in answer.lower()

    def test_very_hungry_agent_mentions_hunger(self):
        answer = _fallback_answer(_ctx(pressure_reasons=["very hungry (75%)"]))
        assert "famished" in answer or "hungry" in answer.lower()

    def test_hungry_agent_mentions_food(self):
        answer = _fallback_answer(_ctx(pressure_reasons=["hungry (35%)"]))
        assert "eaten" in answer or "belly" in answer

    def test_sick_and_very_hungry_combined(self):
        answer = _fallback_answer(
            _ctx(pressure_reasons=["ill", "very hungry (80%)"])
        )
        # The combined-stress branch should fire
        assert "ill" in answer.lower() or "starving" in answer.lower()
        assert "not now" in answer or "beg" in answer

    def test_sick_only_differs_from_very_hungry_only(self):
        sick = _fallback_answer(_ctx(pressure_reasons=["ill"]))
        hungry = _fallback_answer(_ctx(pressure_reasons=["very hungry (70%)"]))
        assert sick != hungry

    def test_stressed_differs_from_healthy(self):
        stressed = _fallback_answer(_ctx(pressure_reasons=["ill"]))
        healthy = _fallback_answer(_ctx(pressure_reasons=[]))
        assert stressed != healthy

    def test_pressure_takes_priority_over_grudge(self):
        """Sick should override grudge detail."""
        answer = _fallback_answer(_ctx(
            pressure_reasons=["ill"],
            relationships=[{"name": "Boris", "status": "foe", "trust": -0.8, "warmth": -0.7}],
        ))
        # Should mention illness, not Boris
        assert "not well" in answer or "ill" in answer.lower()

    def test_pressure_takes_priority_over_memory(self):
        """Very hungry should override memory detail."""
        answer = _fallback_answer(_ctx(
            pressure_reasons=["very hungry (60%)"],
            recent_memories=["Attended the market fair."],
        ))
        assert "famished" in answer or "eaten" in answer
        # Memory detail should not appear
        assert "market fair" not in answer


# ---------------------------------------------------------------------------
# Relationship context
# ---------------------------------------------------------------------------


class TestRelationshipContext:
    def test_grudge_mentioned_by_name(self):
        answer = _fallback_answer(_ctx(
            relationships=[
                {"name": "Boris", "status": "foe", "trust": -0.8, "warmth": -0.6}
            ],
        ))
        assert "Boris" in answer
        assert "troubled" in answer or "weigh" in answer

    def test_ally_mentioned_by_name_when_no_grudge_or_memory(self):
        answer = _fallback_answer(_ctx(
            relationships=[
                {"name": "Elena", "status": "ally", "trust": 0.9, "warmth": 0.8}
            ],
        ))
        assert "Elena" in answer
        assert "grateful" in answer or "help" in answer

    def test_grudge_takes_priority_over_ally(self):
        answer = _fallback_answer(_ctx(
            relationships=[
                {"name": "Elena", "status": "ally", "trust": 0.9, "warmth": 0.8},
                {"name": "Boris", "status": "foe", "trust": -0.7, "warmth": -0.5},
            ],
        ))
        # Foe should appear, ally should not dominate
        assert "Boris" in answer

    def test_no_relationships_no_name_hallucination(self):
        answer = _fallback_answer(_ctx(relationships=[]))
        # Should not invent character names
        assert "Boris" not in answer
        assert "Elena" not in answer


# ---------------------------------------------------------------------------
# Memory context
# ---------------------------------------------------------------------------


class TestMemoryContext:
    def test_recent_memory_referenced(self):
        answer = _fallback_answer(_ctx(
            recent_memories=["Helped repair the mill wheel."],
        ))
        assert "mill wheel" in answer

    def test_last_memory_used_not_first(self):
        """Most recent memory (last in list) should be referenced."""
        answer = _fallback_answer(_ctx(
            recent_memories=[
                "Attended the spring festival.",
                "Traded grain with the merchant.",
                "Witnessed a fire in the storehouse.",
            ],
        ))
        # Last memory should appear
        assert "fire" in answer or "storehouse" in answer

    def test_grudge_takes_priority_over_memory(self):
        answer = _fallback_answer(_ctx(
            relationships=[{"name": "Boris", "status": "foe", "trust": -0.8, "warmth": -0.6}],
            recent_memories=["Harvested grain."],
        ))
        assert "Boris" in answer
        assert "grain" not in answer

    def test_memory_takes_priority_over_ally(self):
        answer = _fallback_answer(_ctx(
            relationships=[{"name": "Elena", "status": "ally", "trust": 0.9, "warmth": 0.8}],
            recent_memories=["Repaired the north wall."],
        ))
        assert "north wall" in answer


# ---------------------------------------------------------------------------
# Generic fallback and determinism
# ---------------------------------------------------------------------------


class TestGenericAndDeterminism:
    def test_no_context_gets_generic_close(self):
        answer = _fallback_answer(_ctx(
            relationships=[],
            recent_memories=[],
            pressure_reasons=[],
        ))
        assert "Perhaps another time" in answer

    def test_deterministic_same_input_same_output(self):
        ctx = _ctx(
            agent_name="Marta",
            profession="healer",
            pressure_reasons=["hungry (30%)"],
            relationships=[{"name": "Boris", "status": "foe", "trust": -0.6, "warmth": -0.5}],
            recent_memories=["Tended a wounded soldier."],
        )
        first = _fallback_answer(ctx)
        second = _fallback_answer(ctx)
        assert first == second

    def test_different_agents_produce_different_responses(self):
        """Simulates the observed bug: 3 villagers all getting the same answer."""
        farmer = _fallback_answer(_ctx(
            agent_name="Aldric", profession="farmer",
            pressure_reasons=[], relationships=[], recent_memories=[],
        ))
        healer = _fallback_answer(_ctx(
            agent_name="Marta", profession="healer",
            pressure_reasons=["ill"], relationships=[], recent_memories=[],
        ))
        soldier = _fallback_answer(_ctx(
            agent_name="Roland", profession="soldier",
            pressure_reasons=[],
            relationships=[{"name": "Boris", "status": "foe", "trust": -0.7, "warmth": -0.5}],
            recent_memories=[],
        ))
        # All three must differ
        assert farmer != healer
        assert healer != soldier
        assert farmer != soldier


# ---------------------------------------------------------------------------
# Dead agent behavior
# ---------------------------------------------------------------------------


class TestDeadAgentResponse:
    """
    Dead agents must never respond like living agents.

    _deceased_response() is the dedicated path; _fallback_answer() delegates
    to it when is_alive=False so that dead state overrides all other context.
    """

    def _dead_ctx(**overrides) -> AgentContextData:
        base = dict(
            agent_id=9,
            agent_name="Marta",
            profession="healer",
            age=42,
            traits={"warmth": 0.8},
            goals=[],
            relationships=[],
            recent_memories=[],
            hunger_pct=90,          # very hungry — must NOT appear in answer
            pressure_reasons=["very hungry (90%)", "ill"],  # must NOT appear
            season="winter",
            weather="blizzard",
            world_name="Ashenvale",
            is_alive=False,
        )
        base.update(overrides)
        return AgentContextData(**base)

    # Make helper a staticmethod-like callable at class scope
    _dead_ctx = staticmethod(_dead_ctx)

    def test_deceased_response_mentions_agent_name(self):
        answer = _deceased_response(self._dead_ctx())
        assert "Marta" in answer

    def test_deceased_response_mentions_profession(self):
        answer = _deceased_response(self._dead_ctx())
        assert "healer" in answer

    def test_deceased_response_indicates_death(self):
        answer = _deceased_response(self._dead_ctx())
        # Must clearly signal the agent is dead
        assert any(word in answer.lower() for word in ("no longer", "passed", "chronicle", "deceased"))

    def test_deceased_response_is_deterministic(self):
        ctx = self._dead_ctx()
        assert _deceased_response(ctx) == _deceased_response(ctx)

    def test_deceased_response_does_not_mention_hunger(self):
        """Death overrides hunger — the dead do not complain of hunger."""
        answer = _deceased_response(self._dead_ctx())
        assert "famished" not in answer
        assert "hungry" not in answer
        assert "eaten" not in answer

    def test_deceased_response_does_not_mention_illness(self):
        answer = _deceased_response(self._dead_ctx())
        assert "not well" not in answer
        assert "ill" not in answer.lower()

    def test_fallback_answer_dead_agent_is_same_as_deceased_response(self):
        """_fallback_answer on a dead context must delegate to _deceased_response."""
        ctx = self._dead_ctx()
        assert _fallback_answer(ctx) == _deceased_response(ctx)

    def test_fallback_dead_overrides_pressure(self):
        """Death overrides sick+very-hungry combined — no living-agent lines."""
        ctx = self._dead_ctx(pressure_reasons=["ill", "very hungry (95%)"])
        answer = _fallback_answer(ctx)
        assert "beg" not in answer
        assert "starving" not in answer
        assert "not now" not in answer

    def test_fallback_dead_overrides_grudge(self):
        ctx = self._dead_ctx(
            pressure_reasons=[],
            relationships=[{"name": "Boris", "status": "foe", "trust": -0.9, "warmth": -0.8}],
        )
        answer = _fallback_answer(ctx)
        # Grudge should not appear in a memorial record
        assert "troubled" not in answer
        assert "Boris" not in answer

    def test_fallback_dead_overrides_memory(self):
        ctx = self._dead_ctx(
            pressure_reasons=[],
            recent_memories=["Repaired the mill wheel."],
        )
        answer = _fallback_answer(ctx)
        assert "mill wheel" not in answer

    def test_fallback_dead_differs_from_living_with_same_pressure(self):
        """Same pressure context — dead vs alive must produce different responses."""
        shared_pressure = ["very hungry (90%)", "ill"]
        dead = _fallback_answer(self._dead_ctx(pressure_reasons=shared_pressure))
        alive = _fallback_answer(_ctx(
            agent_name="Marta", profession="healer",
            pressure_reasons=shared_pressure,
        ))
        assert dead != alive

    def test_different_dead_agents_produce_different_responses(self):
        """Deceased healer and deceased farmer should have different epitaphs."""
        healer = _deceased_response(self._dead_ctx(agent_name="Marta", profession="healer"))
        farmer = _deceased_response(self._dead_ctx(agent_name="Aldric", profession="farmer"))
        assert healer != farmer
