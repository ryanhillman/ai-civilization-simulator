"""
Shared test fixtures.

Phase 7 will expand this with full database fixtures and seeded world state.
"""

from app.models.db import (
    Agent,
    AgentInventory,
    Profession,
    Relationship,
    ResourceType,
    World,
)


def make_world(**kwargs) -> World:
    defaults = {"name": "TestVillage", "current_turn": 0, "current_day": 1}
    return World(**{**defaults, **kwargs})


def make_agent(world_id: int, **kwargs) -> Agent:
    defaults = {
        "world_id": world_id,
        "name": "TestAgent",
        "profession": Profession.farmer,
        "age": 30,
        "personality_traits": {
            "courage": 0.5,
            "greed": 0.3,
            "warmth": 0.5,
            "cunning": 0.3,
            "piety": 0.3,
        },
        "goals": [],
    }
    return Agent(**{**defaults, **kwargs})


def make_inventory(agent_id: int, resource: ResourceType, quantity: float) -> AgentInventory:
    return AgentInventory(agent_id=agent_id, resource_type=resource, quantity=quantity)


def make_relationship(source_id: int, target_id: int, **kwargs) -> Relationship:
    defaults = {
        "source_agent_id": source_id,
        "target_agent_id": target_id,
        "trust": 0.0,
        "warmth": 0.0,
        "respect": 0.0,
        "resentment": 0.0,
        "fear": 0.0,
    }
    return Relationship(**{**defaults, **kwargs})
