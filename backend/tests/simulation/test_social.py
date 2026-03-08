"""
Tests for the social systems — relationship updates and gossip propagation.
"""
import pytest

from app.enums import EventType, Profession
from app.simulation.social.relationships import update_relationships
from app.simulation.social.gossip import spread_gossip
from app.simulation.types import (
    RelationshipState,
    ResolvedAction,
    RumorRecord,
    TurnContext,
)

from tests.simulation.conftest import make_agent_state, make_world_state


# ---------------------------------------------------------------------------
# Relationship updates
# ---------------------------------------------------------------------------


class TestUpdateRelationships:
    def test_heal_agent_creates_warmth_from_patient_to_healer(self, farmer, healer):
        world = make_world_state(agents=[farmer, healer])
        heal = ResolvedAction(
            agent_id=healer.id,
            action_type="heal_agent",
            succeeded=True,
            outcome=f"healed agent {farmer.id}",
            details={"medicine_spent": 1.0, "healed_agent_id": farmer.id},
        )
        ctx = TurnContext(world_state=world, resolved_actions=[heal])
        ctx_out = update_relationships(ctx)

        farmer_to_healer = ctx_out.world_state.relationship(farmer.id, healer.id)
        assert farmer_to_healer is not None
        assert farmer_to_healer.warmth > 0.0
        assert farmer_to_healer.trust > 0.0

    def test_heal_agent_creates_warmth_from_healer_to_patient(self, farmer, healer):
        world = make_world_state(agents=[farmer, healer])
        heal = ResolvedAction(
            agent_id=healer.id,
            action_type="heal_agent",
            succeeded=True,
            outcome=f"healed agent {farmer.id}",
            details={"medicine_spent": 1.0, "healed_agent_id": farmer.id},
        )
        ctx = TurnContext(world_state=world, resolved_actions=[heal])
        ctx_out = update_relationships(ctx)

        healer_to_farmer = ctx_out.world_state.relationship(healer.id, farmer.id)
        assert healer_to_farmer is not None
        assert healer_to_farmer.warmth > 0.0

    def test_trade_food_increases_trust_both_ways(self, farmer, merchant):
        world = make_world_state(agents=[farmer, merchant])
        trade = ResolvedAction(
            agent_id=farmer.id,
            action_type="trade_food",
            succeeded=True,
            outcome="sold 2.0 food to agent 3 for 2.0 coin",
            details={"food_sold": 2.0, "coin_received": 2.0, "buyer_id": merchant.id},
        )
        ctx = TurnContext(world_state=world, resolved_actions=[trade])
        ctx_out = update_relationships(ctx)

        farmer_to_merchant = ctx_out.world_state.relationship(farmer.id, merchant.id)
        merchant_to_farmer = ctx_out.world_state.relationship(merchant.id, farmer.id)
        assert farmer_to_merchant is not None and farmer_to_merchant.trust > 0.0
        assert merchant_to_farmer is not None and merchant_to_farmer.trust > 0.0

    def test_unfair_trade_breeds_buyer_resentment(self, farmer, merchant):
        world = make_world_state(agents=[farmer, merchant])
        # Price 4.0 for 2.0 food = 2.0 coin/unit, which is > 1.5 → unfair
        trade = ResolvedAction(
            agent_id=farmer.id,
            action_type="trade_food",
            succeeded=True,
            outcome="sold 2.0 food to agent 3 for 4.0 coin",
            details={"food_sold": 2.0, "coin_received": 4.0, "buyer_id": merchant.id},
        )
        ctx = TurnContext(world_state=world, resolved_actions=[trade])
        ctx_out = update_relationships(ctx)

        merchant_to_farmer = ctx_out.world_state.relationship(merchant.id, farmer.id)
        assert merchant_to_farmer is not None
        assert merchant_to_farmer.resentment > 0.0

    def test_steal_food_creates_resentment_and_fear_in_victim(self, farmer, soldier):
        world = make_world_state(agents=[farmer, soldier])
        theft = ResolvedAction(
            agent_id=soldier.id,
            action_type="steal_food",
            succeeded=True,
            outcome="stole 2.0 food from agent 1",
            details={"food_stolen": 2.0, "victim_id": farmer.id},
        )
        ctx = TurnContext(world_state=world, resolved_actions=[theft])
        ctx_out = update_relationships(ctx)

        farmer_to_soldier = ctx_out.world_state.relationship(farmer.id, soldier.id)
        assert farmer_to_soldier is not None
        assert farmer_to_soldier.resentment > 0.0
        assert farmer_to_soldier.fear > 0.0

    def test_steal_activates_grudge_after_threshold(self, farmer, soldier):
        # Start with resentment already near threshold
        world = make_world_state(
            agents=[farmer, soldier],
            relationships=[
                RelationshipState(
                    source_agent_id=farmer.id,
                    target_agent_id=soldier.id,
                    resentment=0.3,
                )
            ],
        )
        thefts = [
            ResolvedAction(
                agent_id=soldier.id,
                action_type="steal_food",
                succeeded=True,
                outcome="stole food",
                details={"food_stolen": 2.0, "victim_id": farmer.id},
            )
        ] * 2  # two thefts in one turn (unlikely but tests accumulation)

        ctx = TurnContext(world_state=world, resolved_actions=thefts)
        ctx_out = update_relationships(ctx)

        farmer_to_soldier = ctx_out.world_state.relationship(farmer.id, soldier.id)
        assert farmer_to_soldier is not None
        # resentment should have grown substantially
        assert farmer_to_soldier.resentment >= 0.6  # grudge threshold

    def test_bless_village_increases_trust_toward_priest(self):
        from app.enums import Profession
        priest = make_agent_state(agent_id=10, profession=Profession.priest)
        villager = make_agent_state(agent_id=11, profession=Profession.farmer)
        world = make_world_state(agents=[priest, villager])

        bless = ResolvedAction(
            agent_id=priest.id,
            action_type="bless_village",
            succeeded=True,
            outcome="blessed the village",
            details={},
        )
        ctx = TurnContext(world_state=world, resolved_actions=[bless])
        ctx_out = update_relationships(ctx)

        villager_to_priest = ctx_out.world_state.relationship(villager.id, priest.id)
        assert villager_to_priest is not None
        assert villager_to_priest.trust > 0.0

    def test_failed_action_does_not_update_relationships(self, farmer, healer):
        world = make_world_state(agents=[farmer, healer])
        failed = ResolvedAction(
            agent_id=healer.id,
            action_type="heal_agent",
            succeeded=False,
            outcome="failed to heal",
            details={"healed_agent_id": farmer.id},
        )
        ctx = TurnContext(world_state=world, resolved_actions=[failed])
        ctx_out = update_relationships(ctx)
        assert ctx_out.world_state.relationships == []

    def test_relationship_dimensions_clamped(self, farmer, healer):
        # Start near max trust; should not exceed 1.0
        world = make_world_state(
            agents=[farmer, healer],
            relationships=[
                RelationshipState(
                    source_agent_id=farmer.id,
                    target_agent_id=healer.id,
                    warmth=0.98,
                    trust=0.99,
                )
            ],
        )
        heal = ResolvedAction(
            agent_id=healer.id,
            action_type="heal_agent",
            succeeded=True,
            outcome="healed",
            details={"healed_agent_id": farmer.id},
        )
        ctx = TurnContext(world_state=world, resolved_actions=[heal])
        ctx_out = update_relationships(ctx)
        r = ctx_out.world_state.relationship(farmer.id, healer.id)
        assert r.warmth <= 1.0
        assert r.trust <= 1.0


# ---------------------------------------------------------------------------
# Gossip propagation
# ---------------------------------------------------------------------------


class TestSpreadGossip:
    def _make_rumor(self, world_id=1, turn=1, known_by=None) -> RumorRecord:
        return RumorRecord(
            source_agent_id=99,
            subject_agent_id=99,
            world_id=world_id,
            turn_created=turn,
            turn_expires=turn + 10,
            rumor_type="theft",
            content="Someone stole grain.",
            credibility=0.7,
            known_by=known_by or [99],
        )

    def test_no_spread_without_trust(self, farmer, merchant):
        world = make_world_state(
            agents=[farmer, merchant],
            relationships=[
                RelationshipState(
                    source_agent_id=farmer.id,
                    target_agent_id=merchant.id,
                    trust=0.1,  # below threshold 0.4
                )
            ],
        )
        rumor = self._make_rumor(known_by=[farmer.id])
        world = world.model_copy(update={"active_rumors": [rumor]})
        ctx = TurnContext(world_state=world)
        ctx_out = spread_gossip(ctx)

        updated = ctx_out.world_state.active_rumors[0]
        assert merchant.id not in updated.known_by

    def test_spread_between_high_trust_agents(self, farmer, merchant):
        world = make_world_state(
            agents=[farmer, merchant],
            relationships=[
                RelationshipState(
                    source_agent_id=farmer.id,
                    target_agent_id=merchant.id,
                    trust=0.7,  # above threshold
                )
            ],
        )
        rumor = self._make_rumor(known_by=[farmer.id])
        world = world.model_copy(update={"active_rumors": [rumor]})
        ctx = TurnContext(world_state=world)
        ctx_out = spread_gossip(ctx)

        updated = ctx_out.world_state.active_rumors[0]
        assert merchant.id in updated.known_by

    def test_spread_creates_gossip_event(self, farmer, merchant):
        world = make_world_state(
            agents=[farmer, merchant],
            relationships=[
                RelationshipState(
                    source_agent_id=farmer.id,
                    target_agent_id=merchant.id,
                    trust=0.8,
                )
            ],
        )
        rumor = self._make_rumor(known_by=[farmer.id])
        world = world.model_copy(update={"active_rumors": [rumor]})
        ctx = TurnContext(world_state=world)
        ctx_out = spread_gossip(ctx)

        gossip_events = [e for e in ctx_out.events if e.event_type == EventType.gossip]
        assert len(gossip_events) >= 1

    def test_expired_rumors_pruned(self, farmer):
        world = make_world_state(agents=[farmer], turn=20)
        world = world.model_copy(update={"current_turn": 20})
        expired_rumor = self._make_rumor(turn=1)
        expired_rumor = expired_rumor.model_copy(update={"turn_expires": 10})
        world = world.model_copy(update={"active_rumors": [expired_rumor]})

        ctx = TurnContext(world_state=world)
        ctx_out = spread_gossip(ctx)
        assert ctx_out.world_state.active_rumors == []

    def test_theft_action_creates_theft_rumor(self, farmer, soldier):
        world = make_world_state(agents=[farmer, soldier])
        theft = ResolvedAction(
            agent_id=soldier.id,
            action_type="steal_food",
            succeeded=True,
            outcome="stole 2.0 food from agent 1",
            details={"food_stolen": 2.0, "victim_id": farmer.id},
        )
        ctx = TurnContext(world_state=world, resolved_actions=[theft])
        ctx_out = spread_gossip(ctx)

        theft_rumors = [
            r for r in ctx_out.world_state.active_rumors
            if r.rumor_type == "theft"
        ]
        assert len(theft_rumors) >= 1
        assert theft_rumors[0].subject_agent_id == soldier.id

    def test_hoarding_rumor_created_when_one_agent_has_much_and_others_starve(self):
        hoarder = make_agent_state(agent_id=1, food=25.0, coin=100.0)
        starving = make_agent_state(agent_id=2, food=0.0, coin=0.0, hunger=0.7)
        world = make_world_state(agents=[hoarder, starving])
        ctx = TurnContext(world_state=world)
        ctx_out = spread_gossip(ctx)

        hoarding_rumors = [
            r for r in ctx_out.world_state.active_rumors
            if r.rumor_type == "hoarding"
        ]
        assert len(hoarding_rumors) >= 1
        assert hoarding_rumors[0].subject_agent_id == hoarder.id

    def test_spread_count_increments(self, farmer, merchant):
        world = make_world_state(
            agents=[farmer, merchant],
            relationships=[
                RelationshipState(
                    source_agent_id=farmer.id,
                    target_agent_id=merchant.id,
                    trust=0.9,
                )
            ],
        )
        rumor = self._make_rumor(known_by=[farmer.id])
        world = world.model_copy(update={"active_rumors": [rumor]})
        ctx = TurnContext(world_state=world)
        ctx_out = spread_gossip(ctx)

        updated = ctx_out.world_state.active_rumors[0]
        assert updated.spread_count > 0

    def test_already_known_agents_not_re_added(self, farmer, merchant):
        world = make_world_state(
            agents=[farmer, merchant],
            relationships=[
                RelationshipState(
                    source_agent_id=farmer.id,
                    target_agent_id=merchant.id,
                    trust=0.9,
                )
            ],
        )
        # Merchant already knows the rumor
        rumor = self._make_rumor(known_by=[farmer.id, merchant.id])
        world = world.model_copy(update={"active_rumors": [rumor]})
        ctx = TurnContext(world_state=world)
        ctx_out = spread_gossip(ctx)

        updated = ctx_out.world_state.active_rumors[0]
        # known_by should not have duplicates
        assert updated.known_by.count(merchant.id) == 1
        assert updated.spread_count == 0  # no new spreads


# ---------------------------------------------------------------------------
# Alliance and grudge derivation
# ---------------------------------------------------------------------------


class TestAllianceGrudge:
    def test_alliance_active_when_high_trust_and_warmth(self):
        r = RelationshipState(
            source_agent_id=1, target_agent_id=2,
            trust=0.7, warmth=0.5,
        )
        assert r.alliance_active is True

    def test_no_alliance_when_trust_below_threshold(self):
        r = RelationshipState(
            source_agent_id=1, target_agent_id=2,
            trust=0.5, warmth=0.5,
        )
        assert r.alliance_active is False

    def test_grudge_active_when_resentment_high(self):
        r = RelationshipState(
            source_agent_id=1, target_agent_id=2,
            resentment=0.7,
        )
        assert r.grudge_active is True

    def test_grudge_active_when_fear_high(self):
        r = RelationshipState(
            source_agent_id=1, target_agent_id=2,
            fear=0.6,
        )
        assert r.grudge_active is True

    def test_no_grudge_at_neutral(self):
        r = RelationshipState(source_agent_id=1, target_agent_id=2)
        assert r.grudge_active is False
        assert r.alliance_active is False
