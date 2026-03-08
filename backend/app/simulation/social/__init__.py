"""
Social engine — Phase 3 implementation.

Provides two pipeline stages:

  update_relationships  (insert after "resolve_actions")
  spread_gossip         (insert after "update_relationships")

Usage in build_phase3_pipeline():

    from app.simulation.social import update_relationships, spread_gossip
    pipeline.insert_after("resolve_actions", "update_relationships", update_relationships)
    pipeline.insert_after("update_relationships", "spread_gossip", spread_gossip)

Systems
-------
  update_relationships — adjusts trust/warmth/resentment/fear based on
    actions taken this turn (heal, trade, steal, bless)
  spread_gossip — creates structured RumorRecords from notable events
    and propagates them through the agent trust network
"""
from app.simulation.social.relationships import update_relationships
from app.simulation.social.gossip import spread_gossip

__all__ = ["update_relationships", "spread_gossip"]
