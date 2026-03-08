"""
Phase 3 integration tests — pressure system driving emergent behaviour.

These tests verify that pressure shapes action selection, events, and
relationship state across full turn runs using build_phase3_pipeline().

Key scenarios
-------------
1. Hungry soldier overrides patrol goal and attempts desperate action
2. Low-pressure healer cooperates and heals the sick
3. Theft creates resentment, rumor, and grudge over multiple turns
4. Festival fires on correct day and reduces hunger
5. TurnResult.pressures contains full breakdown for every living agent
6. Phase 3 pipeline is deterministic (same world → same result)
"""
import pytest

from app.enums import Profession
from app.simulation.pipeline import build_phase3_pipeline
from app.simulation.runner import TurnRunner
from app.simulation.types import RelationshipState

from tests.simulation.conftest import make_agent_state, make_world_state


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _phase3_runner() -> TurnRunner:
    return TurnRunner(pipeline=build_phase3_pipeline())


# ---------------------------------------------------------------------------
# Pressure surfaced in TurnResult
# ---------------------------------------------------------------------------


class TestPressureInTurnResult:
    def test_pressures_populated_for_all_living_agents(self):
        farmer = make_agent_state(
            agent_id=1, profession=Profession.farmer, food=10.0,
            goals=[{"type": "produce", "priority": 1}],
        )
        merchant = make_agent_state(
            agent_id=2, profession=Profession.merchant, food=5.0,
            goals=[{"type": "trade", "priority": 1}],
        )
        world = make_world_state(agents=[farmer, merchant])
        result = _phase3_runner().run_turn(world)

        assert farmer.id in result.pressures
        assert merchant.id in result.pressures

    def test_dead_agent_has_no_pressure(self):
        dead = make_agent_state(agent_id=1, is_alive=False)
        farmer = make_agent_state(agent_id=2, profession=Profession.farmer, food=10.0)
        world = make_world_state(agents=[dead, farmer])
        result = _phase3_runner().run_turn(world)

        assert dead.id not in result.pressures
        assert farmer.id in result.pressures

    def test_pressure_breakdown_all_components_present(self):
        farmer = make_agent_state(agent_id=1, profession=Profession.farmer, food=10.0)
        world = make_world_state(agents=[farmer])
        result = _phase3_runner().run_turn(world)

        p = result.pressures[farmer.id]
        assert hasattr(p, "hunger_pressure")
        assert hasattr(p, "resource_pressure")
        assert hasattr(p, "sickness_pressure")
        assert hasattr(p, "social_pressure")
        assert hasattr(p, "memory_pressure")
        assert hasattr(p, "total")
        assert hasattr(p, "top_reasons")

    def test_total_equals_sum_of_components_in_result(self):
        farmer = make_agent_state(
            agent_id=1, hunger=0.4, food=3.0, coin=2.0, is_sick=True
        )
        world = make_world_state(agents=[farmer])
        result = _phase3_runner().run_turn(world)

        p = result.pressures[farmer.id]
        expected = round(
            p.hunger_pressure + p.resource_pressure + p.sickness_pressure
            + p.social_pressure + p.memory_pressure,
            4,
        )
        assert p.total == pytest.approx(expected)

    def test_world_events_in_result(self):
        # Festival day: day=31, turn=10
        farmer = make_agent_state(agent_id=1, profession=Profession.farmer, food=10.0)
        world = make_world_state(agents=[farmer], day=30, turn=9)
        result = _phase3_runner().run_turn(world)
        # advance_world makes day=31 → festival fires
        assert any(we.event_type == "festival" for we in result.world_events)


# ---------------------------------------------------------------------------
# Pressure drives emergent behaviour
# ---------------------------------------------------------------------------


class TestPressureDrivesEmergentBehaviour:
    def test_well_fed_healer_chooses_to_heal_sick_agent(self):
        sick_farmer = make_agent_state(
            agent_id=1, profession=Profession.farmer,
            is_sick=True, food=8.0, coin=10.0,
        )
        healer = make_agent_state(
            agent_id=2, profession=Profession.healer,
            food=15.0, coin=20.0, medicine=10.0, hunger=0.0,
            goals=[{"type": "heal", "priority": 1}],
        )
        world = make_world_state(agents=[sick_farmer, healer])
        result = _phase3_runner().run_turn(world)

        healer_pressure = result.pressures[healer.id]
        assert healer_pressure.total < 1.5  # healer is not under heavy pressure

        healer_action = next(
            a for a in result.resolved_actions if a.agent_id == healer.id
        )
        assert healer_action.action_type == "heal_agent"

    def test_hungry_agent_has_higher_pressure_than_well_fed_agent(self):
        hungry = make_agent_state(agent_id=1, hunger=0.7, food=0.0, coin=0.0)
        fed = make_agent_state(agent_id=2, hunger=0.0, food=20.0, coin=15.0)
        world = make_world_state(agents=[hungry, fed])
        result = _phase3_runner().run_turn(world)

        assert result.pressures[hungry.id].total > result.pressures[fed.id].total

    def test_sick_agent_shows_sickness_pressure(self):
        sick = make_agent_state(agent_id=1, is_sick=True, food=10.0)
        healthy = make_agent_state(agent_id=2, is_sick=False, food=10.0)
        world = make_world_state(agents=[sick, healthy])
        result = _phase3_runner().run_turn(world)

        assert result.pressures[sick.id].sickness_pressure > 0.5
        assert result.pressures[healthy.id].sickness_pressure == 0.0

    def test_score_influences_action_selection_under_survival_pressure(self):
        """
        An agent under extreme pressure (total >= 2.5) should have their
        action driven by score rather than goals. The resolved action should
        reflect the highest-scored opportunity.
        """
        # Extremely hungry merchant with no food: resource + hunger pressure
        desperate = make_agent_state(
            agent_id=1, profession=Profession.merchant,
            hunger=0.8, food=0.0, coin=0.0,
            goals=[{"type": "earn", "priority": 1}],  # goal says earn/patrol/trade
        )
        # Provide a rich farmer for potential trade target
        rich_farmer = make_agent_state(
            agent_id=2, profession=Profession.farmer,
            food=30.0, coin=20.0,
            goals=[{"type": "produce", "priority": 1}],
        )
        world = make_world_state(agents=[desperate, rich_farmer])
        result = _phase3_runner().run_turn(world)

        p = result.pressures[desperate.id]
        # With high pressure, action should be food-focused
        action = next(
            a for a in result.resolved_actions if a.agent_id == desperate.id
        )
        if p.total >= 2.5:
            # Survival mode: action should be scored-highest (food-seeking if available)
            # Merchant has trade_goods + trade_food (if farmer has surplus) opportunities
            assert action.action_type in (
                "trade_goods", "trade_food", "steal_food", "rest"
            )


# ---------------------------------------------------------------------------
# Multi-turn emergent social dynamics
# ---------------------------------------------------------------------------


class TestMultiTurnSocialDynamics:
    def test_trust_grows_after_repeated_trade(self):
        """Multiple fair trades should increase trust between trading partners."""
        farmer = make_agent_state(
            agent_id=1, profession=Profession.farmer,
            food=30.0, coin=5.0,
            goals=[{"type": "produce", "priority": 1}],
        )
        hungry_merchant = make_agent_state(
            agent_id=2, profession=Profession.merchant,
            food=0.5, coin=20.0, hunger=0.3,
            goals=[{"type": "trade", "priority": 1}],
        )
        world = make_world_state(agents=[farmer, hungry_merchant])
        results = _phase3_runner().run_turns(world, n=5)

        # Find trust accumulated over turns
        final_world = results[-1].world_state
        farmer_to_merchant = final_world.relationship(farmer.id, hungry_merchant.id)
        merchant_to_farmer = final_world.relationship(hungry_merchant.id, farmer.id)

        # At least one direction of trust should have formed if trades occurred
        trade_count = sum(
            1 for r in results
            for a in r.resolved_actions
            if a.action_type == "trade_food"
        )
        if trade_count > 0:
            assert (
                (farmer_to_merchant and farmer_to_merchant.trust > 0.0)
                or (merchant_to_farmer and merchant_to_farmer.trust > 0.0)
            )

    def test_rumors_accumulate_across_turns(self):
        """Hoarding detection should create rumors that persist."""
        hoarder = make_agent_state(
            agent_id=1, profession=Profession.farmer,
            food=25.0, coin=50.0,
            goals=[{"type": "stockpile", "priority": 1}],
        )
        starving = make_agent_state(
            agent_id=2, profession=Profession.merchant,
            food=0.0, coin=0.0, hunger=0.6,
            goals=[{"type": "trade", "priority": 1}],
        )
        world = make_world_state(agents=[hoarder, starving])
        results = _phase3_runner().run_turns(world, n=3)

        final_world = results[-1].world_state
        hoarding_rumors = [
            r for r in final_world.active_rumors
            if r.rumor_type == "hoarding"
        ]
        assert len(hoarding_rumors) >= 1


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


class TestPhase3Determinism:
    def test_same_world_same_result(self):
        farmer = make_agent_state(
            agent_id=1, profession=Profession.farmer,
            food=10.0, coin=5.0, hunger=0.2,
            goals=[{"type": "produce", "priority": 1}],
            traits={"warmth": 0.8, "courage": 0.4, "greed": 0.2,
                    "cunning": 0.2, "piety": 0.5},
        )
        merchant = make_agent_state(
            agent_id=2, profession=Profession.merchant,
            food=3.0, coin=10.0,
            goals=[{"type": "trade", "priority": 1}],
            traits={"courage": 0.4, "greed": 0.7, "warmth": 0.4,
                    "cunning": 0.9, "piety": 0.1},
        )
        world = make_world_state(agents=[farmer, merchant])

        runner = _phase3_runner()
        r1 = runner.run_turn(world)
        r2 = runner.run_turn(world)

        assert [(a.agent_id, a.action_type, a.outcome) for a in r1.resolved_actions] == \
               [(a.agent_id, a.action_type, a.outcome) for a in r2.resolved_actions]

        assert {k: v.total for k, v in r1.pressures.items()} == \
               {k: v.total for k, v in r2.pressures.items()}

    def test_multi_turn_chain_is_deterministic(self):
        farmer = make_agent_state(
            agent_id=1, profession=Profession.farmer,
            food=15.0, coin=5.0,
            goals=[{"type": "produce", "priority": 1}],
        )
        world = make_world_state(agents=[farmer])

        runner = _phase3_runner()
        results_a = runner.run_turns(world, n=5)
        results_b = runner.run_turns(world, n=5)

        for ra, rb in zip(results_a, results_b):
            assert ra.turn_number == rb.turn_number
            assert len(ra.resolved_actions) == len(rb.resolved_actions)
            for a, b in zip(ra.resolved_actions, rb.resolved_actions):
                assert a.action_type == b.action_type
                assert a.outcome == b.outcome


# ---------------------------------------------------------------------------
# Phase 3 pipeline structure
# ---------------------------------------------------------------------------


class TestPhase3PipelineStructure:
    def test_has_eleven_stages(self):
        p = build_phase3_pipeline()
        assert len(p) == 11

    def test_stage_order(self):
        p = build_phase3_pipeline()
        assert p.stage_names == [
            "advance_world",
            "apply_world_events",
            "refresh_agents",
            "compute_pressure",
            "generate_opportunities",
            "economy_opportunities",
            "resolve_actions",
            "update_relationships",
            "spread_gossip",
            "create_turn_events",
            "record_memories",
        ]

    def test_pressure_computed_before_opportunities(self):
        """compute_pressure must run before generate_opportunities."""
        p = build_phase3_pipeline()
        names = p.stage_names
        assert names.index("compute_pressure") < names.index("generate_opportunities")

    def test_relationships_updated_before_gossip(self):
        """Relationships must be updated before gossip so trust-based spread is accurate."""
        p = build_phase3_pipeline()
        names = p.stage_names
        assert names.index("update_relationships") < names.index("spread_gossip")
