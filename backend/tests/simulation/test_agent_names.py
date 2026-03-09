"""
Tests ensuring agent names (not numeric IDs) appear in all user-facing text:
  - Turn event descriptions
  - Gossip rumor content
  - Gossip spread event descriptions
  - Memory summaries (which inherit from events)
  - No "Agent {number}" pattern in any output

These tests exercise the text-formatting layer (event_hooks, gossip, action_resolve)
without touching DB or AI services.
"""
from __future__ import annotations

import re

import pytest

from app.enums import EventType, Profession
from app.simulation.social.gossip import spread_gossip
from app.simulation.stages.action_resolve import _resolve, resolve_actions
from app.simulation.stages.event_hooks import create_turn_events
from app.simulation.stages.memory_hooks import record_memories
from app.simulation.types import (
    Opportunity,
    RelationshipState,
    ResolvedAction,
    TurnContext,
)

from tests.simulation.conftest import make_agent_state, make_world_state

# Pattern that should never appear in user-facing text (e.g. "Agent 53")
_AGENT_ID_PATTERN = re.compile(r"\bAgent\s+\d+\b", re.IGNORECASE)


def _no_agent_id(text: str) -> bool:
    """Return True if text contains no 'Agent {number}' substrings."""
    return not _AGENT_ID_PATTERN.search(text)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_harvest_ctx(agent_name: str = "Aldric", agent_id: int = 1):
    agent = make_agent_state(agent_id=agent_id, name=agent_name, food=5.0)
    world = make_world_state(agents=[agent])
    opp = Opportunity(agent_id=agent_id, action_type="harvest_food", score=1.0)
    return TurnContext(world_state=world, opportunities=[opp])


# ---------------------------------------------------------------------------
# Event description tests
# ---------------------------------------------------------------------------


class TestEventDescriptions:
    def test_harvest_event_uses_agent_name(self):
        agent = make_agent_state(agent_id=7, name="Elara", food=5.0)
        world = make_world_state(agents=[agent])
        opp = Opportunity(agent_id=7, action_type="harvest_food", score=1.0)
        ctx = TurnContext(world_state=world, opportunities=[opp])
        ctx_out = create_turn_events(resolve_actions(ctx))

        harvest_events = [e for e in ctx_out.events if e.event_type == EventType.harvest]
        assert harvest_events, "Expected at least one harvest event"
        desc = harvest_events[0].description
        assert "Elara" in desc
        assert _no_agent_id(desc), f"Found 'Agent {{number}}' in: {desc!r}"

    def test_bless_village_event_uses_agent_name(self):
        priest = make_agent_state(agent_id=3, name="Brother Aldus", profession=Profession.priest)
        world = make_world_state(agents=[priest])
        opp = Opportunity(agent_id=3, action_type="bless_village", score=1.0)
        ctx = TurnContext(world_state=world, opportunities=[opp])
        ctx_out = create_turn_events(resolve_actions(ctx))

        festival_events = [e for e in ctx_out.events if e.event_type == EventType.festival]
        assert festival_events, "Expected at least one festival event"
        desc = festival_events[0].description
        assert "Brother Aldus" in desc
        assert _no_agent_id(desc), f"Found 'Agent {{number}}' in: {desc!r}"

    def test_trade_event_uses_both_agent_names(self):
        seller = make_agent_state(agent_id=1, name="Finn", food=20.0, coin=0.0)
        buyer = make_agent_state(agent_id=2, name="Vera", food=0.0, coin=10.0)
        world = make_world_state(agents=[seller, buyer])
        opp = Opportunity(
            agent_id=1,
            action_type="trade_food",
            target_agent_id=2,
            score=1.0,
            metadata={"food_amount": 3.0, "price": 2.0, "buyer_id": 2},
        )
        ctx = TurnContext(world_state=world, opportunities=[opp])
        ctx_out = create_turn_events(resolve_actions(ctx))

        trade_events = [e for e in ctx_out.events if e.event_type == EventType.trade]
        assert trade_events, "Expected at least one trade event"
        desc = trade_events[0].description
        assert "Finn" in desc
        assert "Vera" in desc
        assert _no_agent_id(desc), f"Found 'Agent {{number}}' in: {desc!r}"

    def test_theft_event_uses_both_agent_names(self):
        thief = make_agent_state(agent_id=10, name="Roric", food=0.0)
        victim = make_agent_state(agent_id=20, name="Mira", food=15.0)
        world = make_world_state(agents=[thief, victim])
        opp = Opportunity(
            agent_id=10,
            action_type="steal_food",
            target_agent_id=20,
            score=1.0,
            metadata={"steal_amount": 2.0, "target_id": 20},
        )
        ctx = TurnContext(world_state=world, opportunities=[opp])
        ctx_out = create_turn_events(resolve_actions(ctx))

        theft_events = [e for e in ctx_out.events if e.event_type == EventType.theft]
        assert theft_events, "Expected at least one theft event"
        desc = theft_events[0].description
        assert "Roric" in desc
        assert "Mira" in desc
        assert _no_agent_id(desc), f"Found 'Agent {{number}}' in: {desc!r}"

    def test_heal_event_uses_both_agent_names(self):
        healer = make_agent_state(
            agent_id=5, name="Sable", profession=Profession.healer, medicine=10.0
        )
        patient = make_agent_state(agent_id=6, name="Thorn", is_sick=True)
        world = make_world_state(agents=[healer, patient])
        opp = Opportunity(
            agent_id=5,
            action_type="heal_agent",
            target_agent_id=6,
            score=1.0,
            metadata={"medicine_cost": 1.0},
        )
        ctx = TurnContext(world_state=world, opportunities=[opp])
        ctx_out = create_turn_events(resolve_actions(ctx))

        sickness_events = [e for e in ctx_out.events if e.event_type == EventType.sickness]
        assert sickness_events, "Expected at least one sickness event"
        desc = sickness_events[0].description
        assert "Sable" in desc
        assert "Thorn" in desc
        assert _no_agent_id(desc), f"Found 'Agent {{number}}' in: {desc!r}"

    def test_unknown_agent_falls_back_to_villager(self):
        """If a referenced agent_id isn't in world, text should say 'a villager'."""
        agent = make_agent_state(agent_id=1, name="Aldric")
        world = make_world_state(agents=[agent])
        # Action referencing agent_id=99 which doesn't exist in world
        action = ResolvedAction(
            agent_id=1,
            action_type="trade_food",
            succeeded=True,
            outcome="sold 2.0 food to a villager for 3.0 coin",
            details={"food_sold": 2.0, "coin_received": 3.0, "buyer_id": 99},
        )
        ctx = TurnContext(world_state=world, resolved_actions=[action])
        ctx_out = create_turn_events(ctx)

        trade_events = [e for e in ctx_out.events if e.event_type == EventType.trade]
        assert trade_events
        desc = trade_events[0].description
        assert "Agent 99" not in desc
        assert _no_agent_id(desc), f"Found 'Agent {{number}}' in: {desc!r}"


# ---------------------------------------------------------------------------
# Memory summary tests (inherits from event description)
# ---------------------------------------------------------------------------


class TestMemorySummaries:
    def test_memory_summary_uses_agent_name_not_id(self):
        agent = make_agent_state(agent_id=42, name="Lyra", food=5.0)
        world = make_world_state(agents=[agent])
        opp = Opportunity(agent_id=42, action_type="harvest_food", score=1.0)
        ctx = TurnContext(world_state=world, opportunities=[opp])
        ctx_out = record_memories(create_turn_events(resolve_actions(ctx)))

        assert ctx_out.memories, "Expected at least one memory"
        for mem in ctx_out.memories:
            assert _no_agent_id(mem.summary), (
                f"Found 'Agent {{number}}' in memory: {mem.summary!r}"
            )
        summaries = [m.summary for m in ctx_out.memories]
        assert any("Lyra" in s for s in summaries), "Agent name missing from memories"

    def test_theft_memory_uses_both_names(self):
        thief = make_agent_state(agent_id=11, name="Cole", food=0.0)
        victim = make_agent_state(agent_id=22, name="Wren", food=15.0)
        world = make_world_state(agents=[thief, victim])
        opp = Opportunity(
            agent_id=11,
            action_type="steal_food",
            target_agent_id=22,
            score=1.0,
            metadata={"steal_amount": 2.0, "target_id": 22},
        )
        ctx = TurnContext(world_state=world, opportunities=[opp])
        ctx_out = record_memories(create_turn_events(resolve_actions(ctx)))

        theft_mems = [m for m in ctx_out.memories if m.event_type == EventType.theft]
        assert theft_mems, "Expected theft memories"
        for mem in theft_mems:
            assert _no_agent_id(mem.summary), (
                f"Found 'Agent {{number}}' in theft memory: {mem.summary!r}"
            )


# ---------------------------------------------------------------------------
# Gossip rumor content tests
# ---------------------------------------------------------------------------


class TestGossipRumorContent:
    def test_theft_rumor_uses_agent_names(self):
        thief = make_agent_state(agent_id=1, name="Roric", food=0.0)
        victim = make_agent_state(agent_id=2, name="Mira", food=15.0)
        world = make_world_state(agents=[thief, victim])
        theft = ResolvedAction(
            agent_id=1,
            action_type="steal_food",
            succeeded=True,
            outcome="stole 2.0 food",
            details={"food_stolen": 2.0, "victim_id": 2},
        )
        ctx = TurnContext(world_state=world, resolved_actions=[theft])
        ctx_out = spread_gossip(ctx)

        theft_rumors = [r for r in ctx_out.world_state.active_rumors if r.rumor_type == "theft"]
        assert theft_rumors
        content = theft_rumors[0].content
        assert "Roric" in content, f"Thief name missing from rumor: {content!r}"
        assert "Mira" in content, f"Victim name missing from rumor: {content!r}"
        assert _no_agent_id(content), f"Found 'Agent {{number}}' in rumor: {content!r}"

    def test_hoarding_rumor_uses_agent_name_not_id(self):
        hoarder = make_agent_state(agent_id=5, name="Gregor", food=30.0)
        starving = make_agent_state(agent_id=6, name="Pip", food=0.0)
        world = make_world_state(agents=[hoarder, starving])
        ctx = TurnContext(world_state=world)
        ctx_out = spread_gossip(ctx)

        hoarding = [r for r in ctx_out.world_state.active_rumors if r.rumor_type == "hoarding"]
        assert hoarding
        content = hoarding[0].content
        assert "Gregor" in content, f"Hoarder name missing: {content!r}"
        assert "Agent 5" not in content, f"Numeric ID still present: {content!r}"
        assert _no_agent_id(content), f"Found 'Agent {{number}}' in rumor: {content!r}"

    def test_sickness_rumor_uses_name_no_id(self):
        healer = make_agent_state(
            agent_id=1, name="Sable", profession=Profession.healer, medicine=10.0
        )
        patient = make_agent_state(agent_id=2, name="Thorn", is_sick=True)
        world = make_world_state(agents=[healer, patient])
        heal = ResolvedAction(
            agent_id=1,
            action_type="heal_agent",
            succeeded=True,
            outcome="healed Thorn",
            details={"medicine_spent": 1.0, "healed_agent_id": 2},
        )
        ctx = TurnContext(world_state=world, resolved_actions=[heal])
        ctx_out = spread_gossip(ctx)

        sick_rumors = [r for r in ctx_out.world_state.active_rumors if r.rumor_type == "sickness"]
        assert sick_rumors
        content = sick_rumors[0].content
        assert "Thorn" in content, f"Patient name missing: {content!r}"
        assert "agent 2" not in content.lower(), f"Numeric ID still present: {content!r}"
        assert _no_agent_id(content), f"Found 'Agent {{number}}' in rumor: {content!r}"


# ---------------------------------------------------------------------------
# Gossip spread event description tests
# ---------------------------------------------------------------------------


class TestGossipSpreadEvents:
    def test_gossip_spread_event_uses_listener_name(self):
        from app.simulation.types import RumorRecord

        spreader = make_agent_state(agent_id=1, name="Finn", food=5.0)
        listener = make_agent_state(agent_id=2, name="Vera", food=5.0)
        world = make_world_state(
            agents=[spreader, listener],
            relationships=[
                RelationshipState(
                    source_agent_id=1,
                    target_agent_id=2,
                    trust=0.9,
                )
            ],
        )
        rumor = RumorRecord(
            source_agent_id=1,
            subject_agent_id=99,
            world_id=1,
            turn_created=1,
            turn_expires=20,
            rumor_type="theft",
            content="Someone stole from the storehouse.",
            credibility=0.7,
            known_by=[1],
        )
        world = world.model_copy(update={"active_rumors": [rumor]})
        ctx = TurnContext(world_state=world)
        ctx_out = spread_gossip(ctx)

        gossip_events = [e for e in ctx_out.events if e.event_type == EventType.gossip]
        assert gossip_events, "Expected at least one gossip event"
        desc = gossip_events[0].description
        assert "Vera" in desc, f"Listener name missing from gossip event: {desc!r}"
        assert _no_agent_id(desc), f"Found 'Agent {{number}}' in gossip event: {desc!r}"


# ---------------------------------------------------------------------------
# Resolve outcome string tests (direct _resolve calls with world)
# ---------------------------------------------------------------------------


class TestResolveOutcomeStrings:
    def test_trade_food_outcome_uses_buyer_name(self):
        seller = make_agent_state(agent_id=1, name="Finn", food=20.0, coin=0.0)
        buyer = make_agent_state(agent_id=2, name="Vera")
        world = make_world_state(agents=[seller, buyer])
        opp = Opportunity(
            agent_id=1,
            action_type="trade_food",
            target_agent_id=2,
            metadata={"food_amount": 2.0, "price": 3.0, "buyer_id": 2},
        )
        action, _ = _resolve(opp, seller, world)
        assert "Vera" in action.outcome
        assert _no_agent_id(action.outcome), f"Found 'Agent {{number}}' in outcome: {action.outcome!r}"

    def test_steal_food_outcome_uses_victim_name(self):
        thief = make_agent_state(agent_id=1, name="Roric", food=0.0)
        victim = make_agent_state(agent_id=2, name="Mira", food=10.0)
        world = make_world_state(agents=[thief, victim])
        opp = Opportunity(
            agent_id=1,
            action_type="steal_food",
            target_agent_id=2,
            metadata={"steal_amount": 2.0, "target_id": 2},
        )
        action, _ = _resolve(opp, thief, world)
        assert "Mira" in action.outcome
        assert _no_agent_id(action.outcome), f"Found 'Agent {{number}}' in outcome: {action.outcome!r}"

    def test_heal_agent_outcome_uses_patient_name(self):
        healer = make_agent_state(
            agent_id=1, name="Sable", profession=Profession.healer, medicine=10.0
        )
        patient = make_agent_state(agent_id=2, name="Thorn", is_sick=True)
        world = make_world_state(agents=[healer, patient])
        opp = Opportunity(
            agent_id=1,
            action_type="heal_agent",
            target_agent_id=2,
            metadata={"medicine_cost": 1.0},
        )
        action, _ = _resolve(opp, healer, world)
        assert "Thorn" in action.outcome
        assert _no_agent_id(action.outcome), f"Found 'Agent {{number}}' in outcome: {action.outcome!r}"

    def test_resolve_without_world_falls_back_gracefully(self):
        """Existing 2-arg call signature still works; uses 'agent {id}' fallback."""
        seller = make_agent_state(agent_id=1, name="Finn", food=20.0, coin=0.0)
        opp = Opportunity(
            agent_id=1,
            action_type="trade_food",
            target_agent_id=2,
            metadata={"food_amount": 2.0, "price": 3.0, "buyer_id": 2},
        )
        action, _ = _resolve(opp, seller)  # no world — old call signature
        assert action.action_type == "trade_food"
        assert action.succeeded is True
