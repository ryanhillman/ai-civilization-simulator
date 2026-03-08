"""
Social — Relationship Updates

Adjusts relationship dimensions (trust, warmth, resentment, fear) based on
actions resolved this turn.

Rules
-----
  heal_agent   → healed agent gains warmth +0.15, trust +0.10 toward healer
                 healer gains warmth +0.05 toward patient
  trade_food   → both parties gain trust +0.05
                 if price was fair (price <= season_base + 0.1): no resentment
                 if price was high (price > season_base + 0.5): buyer gains
                   resentment +0.10 toward seller
  steal_food   → victim gains resentment +0.40, fear +0.10 toward thief
                 thief gains fear +0.05 toward victim (retaliation fear)
  bless_village → all living agents gain trust +0.02 toward priest

Derived state (alliance_active, grudge_active) is a property on
RelationshipState, computed fresh from the updated dimensions each access.
No separate threshold-crossing event is needed.

All dimensions are clamped to their valid ranges after each update:
  trust, warmth, respect: -1.0..1.0
  resentment, fear:        0.0..1.0
"""
from __future__ import annotations

from app.simulation.types import RelationshipState, ResolvedAction, TurnContext


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clamp_signed(v: float) -> float:
    return max(-1.0, min(1.0, round(v, 4)))


def _clamp_positive(v: float) -> float:
    return max(0.0, min(1.0, round(v, 4)))


def _upsert(
    rels: list[RelationshipState],
    source_id: int,
    target_id: int,
    *,
    trust: float = 0.0,
    warmth: float = 0.0,
    respect: float = 0.0,
    resentment: float = 0.0,
    fear: float = 0.0,
) -> None:
    """Mutate the relationship list in place (already a mutable copy)."""
    for i, r in enumerate(rels):
        if r.source_agent_id == source_id and r.target_agent_id == target_id:
            rels[i] = r.model_copy(update={
                "trust":      _clamp_signed(r.trust + trust),
                "warmth":     _clamp_signed(r.warmth + warmth),
                "respect":    _clamp_signed(r.respect + respect),
                "resentment": _clamp_positive(r.resentment + resentment),
                "fear":       _clamp_positive(r.fear + fear),
            })
            return
    # Relationship does not exist yet — create it
    rels.append(RelationshipState(
        source_agent_id=source_id,
        target_agent_id=target_id,
        trust=_clamp_signed(trust),
        warmth=_clamp_signed(warmth),
        respect=_clamp_signed(respect),
        resentment=_clamp_positive(resentment),
        fear=_clamp_positive(fear),
    ))


# ---------------------------------------------------------------------------
# Stage entry point
# ---------------------------------------------------------------------------


def update_relationships(ctx: TurnContext) -> TurnContext:
    """
    Update relationship dimensions from this turn's resolved actions.

    Operates on a mutable copy of the relationship list; returns an updated
    WorldState with the new relationship snapshot.
    """
    rels: list[RelationshipState] = list(ctx.world_state.relationships)
    living_ids = {a.id for a in ctx.world_state.living_agents}

    for action in ctx.resolved_actions:
        if not action.succeeded:
            continue

        if action.action_type == "heal_agent":
            patient_id = action.details.get("healed_agent_id")
            healer_id = action.agent_id
            if patient_id:
                # Patient feels warmer and more trusting toward healer
                _upsert(rels, patient_id, healer_id, warmth=+0.15, trust=+0.10)
                # Healer feels warmer toward patient
                _upsert(rels, healer_id, patient_id, warmth=+0.05)

        elif action.action_type == "trade_food":
            seller_id = action.agent_id
            buyer_id = action.details.get("buyer_id")
            price = action.details.get("coin_received", 0.0)
            food = action.details.get("food_sold", 0.0)
            if buyer_id:
                # Both parties gain trust from a completed trade
                _upsert(rels, seller_id, buyer_id, trust=+0.05)
                _upsert(rels, buyer_id, seller_id, trust=+0.05)
                # Unfair pricing (>1.0 coin per food unit) breeds resentment
                if food > 0 and (price / food) > 1.5:
                    _upsert(rels, buyer_id, seller_id, resentment=+0.10)

        elif action.action_type == "steal_food":
            thief_id = action.agent_id
            victim_id = action.details.get("victim_id")
            if victim_id:
                # Victim builds strong resentment and fear toward thief
                _upsert(rels, victim_id, thief_id, resentment=+0.40, fear=+0.10)
                # Thief fears retaliation
                _upsert(rels, thief_id, victim_id, fear=+0.05)

        elif action.action_type == "bless_village":
            priest_id = action.agent_id
            for lid in living_ids:
                if lid != priest_id:
                    _upsert(rels, lid, priest_id, trust=+0.02)

    updated_world = ctx.world_state.model_copy(update={"relationships": rels})
    return ctx.model_copy(update={"world_state": updated_world})
