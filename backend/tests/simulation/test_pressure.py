"""
Tests for the agent pressure system.

All tests are pure — no DB, no I/O, no randomness.
"""
import pytest

from app.enums import EventType, Profession
from app.simulation.pressure import (
    SICKNESS_PRESSURE_VALUE,
    _hunger_component,
    _memory_component,
    _resource_component,
    _sickness_component,
    _social_component,
    compute_agent_pressure,
    score_opportunity,
)
from app.simulation.types import (
    AgentPressure,
    InventorySnapshot,
    MemoryRecord,
    Opportunity,
    RelationshipState,
)

from tests.simulation.conftest import make_agent_state, make_world_state


# ---------------------------------------------------------------------------
# hunger_pressure
# ---------------------------------------------------------------------------


class TestHungerPressure:
    def test_zero_hunger_gives_zero_pressure(self, farmer):
        p, _ = _hunger_component(farmer)
        assert p == 0.0

    def test_hunger_pressure_equals_hunger_value(self):
        agent = make_agent_state(hunger=0.7)
        p, _ = _hunger_component(agent)
        assert p == pytest.approx(0.7)

    def test_hunger_pressure_capped_at_one(self):
        agent = make_agent_state(hunger=1.2)
        p, _ = _hunger_component(agent)
        assert p == 1.0

    def test_reason_populated_at_threshold(self):
        agent = make_agent_state(hunger=0.3)
        _, reason = _hunger_component(agent)
        assert reason is not None
        assert "hunger" in reason.lower()

    def test_no_reason_below_threshold(self):
        agent = make_agent_state(hunger=0.2)
        _, reason = _hunger_component(agent)
        assert reason is None


# ---------------------------------------------------------------------------
# resource_pressure
# ---------------------------------------------------------------------------


class TestResourcePressure:
    def test_plenty_of_food_and_coin_gives_zero(self):
        agent = make_agent_state(food=50.0, coin=20.0)
        p, _ = _resource_component(agent)
        assert p == 0.0

    def test_no_food_gives_high_pressure(self):
        agent = make_agent_state(food=0.0, coin=0.0)
        p, _ = _resource_component(agent)
        assert p > 0.5

    def test_no_food_no_coin_is_max_pressure(self):
        agent = make_agent_state(food=0.0, coin=0.0)
        p_low, _ = _resource_component(agent)
        agent_rich = make_agent_state(food=0.0, coin=15.0)
        p_high, _ = _resource_component(agent_rich)
        # No coin adds to pressure but food is dominant (0.7 weight)
        assert p_low > p_high

    def test_blacksmith_needs_more_food_than_priest(self):
        priest = make_agent_state(food=2.0, profession=Profession.priest)
        blacksmith = make_agent_state(food=2.0, profession=Profession.blacksmith)
        p_priest, _ = _resource_component(priest)
        p_bs, _ = _resource_component(blacksmith)
        # Blacksmith eats 1.2/turn, priest eats 0.7/turn → blacksmith more pressured
        assert p_bs > p_priest

    def test_reason_includes_food_info_when_scarce(self):
        agent = make_agent_state(food=0.5, coin=0.0)
        _, reason = _resource_component(agent)
        assert reason is not None
        assert "food" in reason.lower() or "scarce" in reason.lower()


# ---------------------------------------------------------------------------
# sickness_pressure
# ---------------------------------------------------------------------------


class TestSicknessPressure:
    def test_healthy_agent_has_zero_sickness_pressure(self, farmer):
        p, _ = _sickness_component(farmer)
        assert p == 0.0

    def test_sick_agent_has_fixed_pressure(self, farmer):
        sick = farmer.model_copy(update={"is_sick": True})
        p, reason = _sickness_component(sick)
        assert p == SICKNESS_PRESSURE_VALUE
        assert reason == "is sick"


# ---------------------------------------------------------------------------
# social_pressure
# ---------------------------------------------------------------------------


class TestSocialPressure:
    def test_no_relationships_gives_zero(self, farmer):
        world = make_world_state()
        p, _ = _social_component(farmer, world.relationships)
        assert p == 0.0

    def test_high_resentment_gives_pressure(self, farmer):
        rels = [
            RelationshipState(
                source_agent_id=99,
                target_agent_id=farmer.id,
                resentment=0.8,
            )
        ]
        p, _ = _social_component(farmer, rels)
        assert p > 0.0

    def test_grudge_gives_extra_pressure(self, farmer):
        # A grudge (resentment >= 0.6) adds 0.2 per grudge
        rels_no_grudge = [
            RelationshipState(
                source_agent_id=99,
                target_agent_id=farmer.id,
                resentment=0.3,
            )
        ]
        rels_grudge = [
            RelationshipState(
                source_agent_id=99,
                target_agent_id=farmer.id,
                resentment=0.8,  # >= 0.6 → grudge_active
            )
        ]
        p_no, _ = _social_component(farmer, rels_no_grudge)
        p_yes, reason = _social_component(farmer, rels_grudge)
        assert p_yes > p_no
        assert reason is not None and "grudge" in reason.lower()

    def test_outgoing_resentment_does_not_affect_target(self, farmer, merchant):
        # farmer resents merchant; this should NOT pressure farmer
        rels = [
            RelationshipState(
                source_agent_id=farmer.id,
                target_agent_id=merchant.id,
                resentment=0.9,
            )
        ]
        p, _ = _social_component(farmer, rels)
        assert p == 0.0


# ---------------------------------------------------------------------------
# memory_pressure
# ---------------------------------------------------------------------------


class TestMemoryPressure:
    def test_no_memories_gives_zero(self, farmer):
        p, _ = _memory_component(farmer)
        assert p == 0.0

    def test_positive_memories_give_zero_pressure(self, farmer):
        farmer_happy = farmer.model_copy(update={"recent_memories": [
            MemoryRecord(
                agent_id=farmer.id, world_id=1, turn_number=1,
                event_type=EventType.festival,
                summary="Great festival!", emotional_weight=0.5,
            )
        ]})
        p, _ = _memory_component(farmer_happy)
        assert p == 0.0

    def test_negative_memories_give_pressure(self, farmer):
        farmer_traumatised = farmer.model_copy(update={"recent_memories": [
            MemoryRecord(
                agent_id=farmer.id, world_id=1, turn_number=1,
                event_type=EventType.theft,
                summary="Was robbed.", emotional_weight=-0.7,
            )
        ]})
        p, _ = _memory_component(farmer_traumatised)
        assert p > 0.0

    def test_multiple_traumas_stack(self, farmer):
        memories = [
            MemoryRecord(
                agent_id=farmer.id, world_id=1, turn_number=i,
                event_type=EventType.conflict,
                summary=f"Conflict {i}", emotional_weight=-0.4,
            )
            for i in range(5)
        ]
        farmer_stressed = farmer.model_copy(update={"recent_memories": memories})
        p, _ = _memory_component(farmer_stressed)
        farmer_single = farmer.model_copy(update={"recent_memories": [memories[0]]})
        p_single, _ = _memory_component(farmer_single)
        assert p > p_single


# ---------------------------------------------------------------------------
# compute_agent_pressure (integration)
# ---------------------------------------------------------------------------


class TestComputeAgentPressure:
    def test_total_equals_sum_of_components(self, farmer):
        world = make_world_state(agents=[farmer])
        p = compute_agent_pressure(farmer, world)
        expected = round(
            p.hunger_pressure + p.resource_pressure + p.sickness_pressure
            + p.social_pressure + p.memory_pressure,
            4,
        )
        assert p.total == expected

    def test_calm_well_fed_agent_has_low_total(self):
        agent = make_agent_state(hunger=0.0, food=50.0, coin=20.0)
        world = make_world_state(agents=[agent])
        p = compute_agent_pressure(agent, world)
        assert p.total < 0.5

    def test_starving_sick_agent_has_high_total(self):
        agent = make_agent_state(
            hunger=0.8, food=0.0, coin=0.0, is_sick=True
        )
        world = make_world_state(agents=[agent])
        p = compute_agent_pressure(agent, world)
        assert p.total > 2.0

    def test_top_reasons_lists_highest_contributors_first(self):
        agent = make_agent_state(hunger=0.9, is_sick=True, food=0.0, coin=0.0)
        world = make_world_state(agents=[agent])
        p = compute_agent_pressure(agent, world)
        assert len(p.top_reasons) >= 2
        # Sickness (0.8) and hunger (0.9) should both appear
        combined = " ".join(p.top_reasons).lower()
        assert "sick" in combined or "hunger" in combined

    def test_pressure_is_deterministic(self, farmer):
        world = make_world_state(agents=[farmer])
        p1 = compute_agent_pressure(farmer, world)
        p2 = compute_agent_pressure(farmer, world)
        assert p1 == p2

    def test_relationship_contributes_to_social_pressure(self, farmer, merchant):
        world_with_grudge = make_world_state(
            agents=[farmer, merchant],
            relationships=[
                RelationshipState(
                    source_agent_id=merchant.id,
                    target_agent_id=farmer.id,
                    resentment=0.9,
                )
            ],
        )
        world_clean = make_world_state(agents=[farmer, merchant])
        p_grudge = compute_agent_pressure(farmer, world_with_grudge)
        p_clean = compute_agent_pressure(farmer, world_clean)
        assert p_grudge.social_pressure > p_clean.social_pressure


# ---------------------------------------------------------------------------
# score_opportunity
# ---------------------------------------------------------------------------


class TestScoreOpportunity:
    def test_baseline_score_is_one_without_pressure(self):
        opp = Opportunity(agent_id=1, action_type="harvest_food")
        scored = score_opportunity(opp, None)
        assert scored.score == 1.0

    def test_hungry_agent_scores_food_seeking_higher(self):
        pressure = AgentPressure(
            agent_id=1,
            hunger_pressure=0.8,
            resource_pressure=0.0,
            sickness_pressure=0.0,
            social_pressure=0.0,
            memory_pressure=0.0,
            total=0.8,
        )
        food_opp = Opportunity(agent_id=1, action_type="harvest_food")
        rest_opp = Opportunity(agent_id=1, action_type="rest")
        scored_food = score_opportunity(food_opp, pressure)
        scored_rest = score_opportunity(rest_opp, pressure)
        assert scored_food.score > scored_rest.score

    def test_sick_agent_scores_healing_highest(self):
        pressure = AgentPressure(
            agent_id=1,
            hunger_pressure=0.0,
            resource_pressure=0.0,
            sickness_pressure=0.8,
            social_pressure=0.0,
            memory_pressure=0.0,
            total=0.8,
        )
        heal_opp = Opportunity(agent_id=1, action_type="heal_self")
        harvest_opp = Opportunity(agent_id=1, action_type="harvest_food")
        assert score_opportunity(heal_opp, pressure).score > score_opportunity(harvest_opp, pressure).score

    def test_low_pressure_boosts_cooperative_actions(self):
        low_pressure = AgentPressure(
            agent_id=1,
            hunger_pressure=0.0,
            resource_pressure=0.1,
            sickness_pressure=0.0,
            social_pressure=0.0,
            memory_pressure=0.0,
            total=0.1,
        )
        high_pressure = AgentPressure(
            agent_id=1,
            hunger_pressure=0.4,
            resource_pressure=0.4,
            sickness_pressure=0.0,
            social_pressure=0.4,
            memory_pressure=0.0,
            total=1.2,
        )
        opp = Opportunity(agent_id=1, action_type="heal_agent")
        score_low = score_opportunity(opp, low_pressure).score
        score_high = score_opportunity(opp, high_pressure).score
        assert score_low > score_high

    def test_social_pressure_reduces_generosity(self):
        pressure = AgentPressure(
            agent_id=1,
            hunger_pressure=0.0,
            resource_pressure=0.0,
            sickness_pressure=0.0,
            social_pressure=0.6,
            memory_pressure=0.0,
            total=0.6,
        )
        bless_opp = Opportunity(agent_id=1, action_type="bless_village")
        scored = score_opportunity(bless_opp, pressure)
        assert scored.score < 1.0  # reduced from baseline

    def test_extreme_pressure_boosts_steal_food(self):
        pressure = AgentPressure(
            agent_id=1,
            hunger_pressure=1.0,
            resource_pressure=1.0,
            sickness_pressure=0.8,
            social_pressure=0.5,
            memory_pressure=0.2,
            total=3.5,
        )
        steal_opp = Opportunity(agent_id=1, action_type="steal_food")
        rest_opp = Opportunity(agent_id=1, action_type="rest")
        assert score_opportunity(steal_opp, pressure).score > score_opportunity(rest_opp, pressure).score
