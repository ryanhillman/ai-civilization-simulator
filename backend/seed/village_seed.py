"""
Seed the database with the initial village state.

Run from the backend/ directory:
    uv run python seed/village_seed.py

This script is idempotent: it drops the existing world named "Ashenvale"
and recreates it fresh each time.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.models.db import (
    Agent,
    AgentInventory,
    Profession,
    Relationship,
    ResourceType,
    World,
)

# ---------------------------------------------------------------------------
# Village definition
# ---------------------------------------------------------------------------

WORLD_NAME = "Ashenvale"

AGENTS = [
    {
        "name": "Aldric",
        "profession": Profession.farmer,
        "age": 42,
        "personality_traits": {
            "courage": 0.4,
            "greed": 0.2,
            "warmth": 0.8,
            "cunning": 0.2,
            "piety": 0.5,
        },
        "goals": [
            {"type": "produce", "target": "food", "priority": 1},
            {"type": "protect", "target": "family", "priority": 2},
        ],
        "inventory": {
            ResourceType.food: 18.0,
            ResourceType.coin: 5.0,
            ResourceType.wood: 8.0,
            ResourceType.medicine: 1.0,
        },
    },
    {
        "name": "Marta",
        "profession": Profession.healer,
        "age": 35,
        "personality_traits": {
            "courage": 0.5,
            "greed": 0.1,
            "warmth": 0.9,
            "cunning": 0.4,
            "piety": 0.6,
        },
        "goals": [
            {"type": "heal", "target": "villagers", "priority": 1},
            {"type": "stockpile", "target": "medicine", "priority": 2},
        ],
        "inventory": {
            ResourceType.food: 10.0,
            ResourceType.coin: 12.0,
            ResourceType.wood: 4.0,
            ResourceType.medicine: 15.0,
        },
    },
    {
        "name": "Gregor",
        "profession": Profession.blacksmith,
        "age": 51,
        "personality_traits": {
            "courage": 0.8,
            "greed": 0.3,
            "warmth": 0.3,
            "cunning": 0.4,
            "piety": 0.2,
        },
        "goals": [
            {"type": "produce", "target": "tools", "priority": 1},
            {"type": "accumulate", "target": "coin", "priority": 2},
        ],
        "inventory": {
            ResourceType.food: 8.0,
            ResourceType.coin: 20.0,
            ResourceType.wood: 15.0,
            ResourceType.medicine: 0.0,
        },
    },
    {
        "name": "Elena",
        "profession": Profession.merchant,
        "age": 29,
        "personality_traits": {
            "courage": 0.4,
            "greed": 0.7,
            "warmth": 0.4,
            "cunning": 0.9,
            "piety": 0.1,
        },
        "goals": [
            {"type": "trade", "target": "profit", "priority": 1},
            {"type": "accumulate", "target": "coin", "priority": 2},
        ],
        "inventory": {
            ResourceType.food: 12.0,
            ResourceType.coin: 35.0,
            ResourceType.wood: 6.0,
            ResourceType.medicine: 3.0,
        },
    },
    {
        "name": "Brother Cael",
        "profession": Profession.priest,
        "age": 58,
        "personality_traits": {
            "courage": 0.5,
            "greed": 0.05,
            "warmth": 0.85,
            "cunning": 0.3,
            "piety": 0.99,
        },
        "goals": [
            {"type": "maintain", "target": "harmony", "priority": 1},
            {"type": "tend", "target": "shrine", "priority": 2},
        ],
        "inventory": {
            ResourceType.food: 9.0,
            ResourceType.coin: 8.0,
            ResourceType.wood: 5.0,
            ResourceType.medicine: 4.0,
        },
    },
    {
        "name": "Roland",
        "profession": Profession.soldier,
        "age": 33,
        "personality_traits": {
            "courage": 0.9,
            "greed": 0.3,
            "warmth": 0.4,
            "cunning": 0.5,
            "piety": 0.3,
        },
        "goals": [
            {"type": "protect", "target": "village", "priority": 1},
            {"type": "earn", "target": "coin", "priority": 2},
        ],
        "inventory": {
            ResourceType.food: 10.0,
            ResourceType.coin: 15.0,
            ResourceType.wood: 3.0,
            ResourceType.medicine: 2.0,
        },
    },
]

# Directed relationship seeds.
# Format: (source_name, target_name, trust, warmth, respect, resentment, fear)
# All values: -1.0..1.0
RELATIONSHIPS = [
    # Aldric trusts Marta — she saved his daughter from fever last winter
    ("Aldric", "Marta",       0.75, 0.70, 0.60, 0.00, 0.00),
    ("Marta", "Aldric",       0.65, 0.60, 0.50, 0.00, 0.00),

    # Aldric and Brother Cael — old friends, pious bond
    ("Aldric", "Brother Cael", 0.60, 0.65, 0.70, 0.00, 0.00),
    ("Brother Cael", "Aldric", 0.60, 0.55, 0.55, 0.00, 0.00),

    # Gregor and Roland — mutual professional respect, share a drink
    ("Gregor", "Roland",      0.50, 0.40, 0.70, 0.00, 0.00),
    ("Roland", "Gregor",      0.50, 0.45, 0.65, 0.00, 0.00),

    # Gregor distrusts Elena — she once tried to undersell his tools
    ("Gregor", "Elena",      -0.30, -0.10, 0.10, 0.40, 0.00),
    ("Elena", "Gregor",       0.10, 0.20, 0.40, 0.00, 0.10),

    # Roland resents Elena — she cheated him on a trade deal
    ("Roland", "Elena",      -0.20, -0.10, 0.10, 0.55, 0.00),
    ("Elena", "Roland",       0.30, 0.20, 0.30, 0.00, 0.15),

    # Brother Cael is trusted by everyone — fill remaining pairs with mild warmth
    ("Brother Cael", "Marta",  0.60, 0.65, 0.55, 0.00, 0.00),
    ("Marta", "Brother Cael",  0.65, 0.70, 0.65, 0.00, 0.00),
    ("Brother Cael", "Elena",  0.30, 0.35, 0.20, 0.00, 0.00),
    ("Elena", "Brother Cael",  0.45, 0.30, 0.50, 0.00, 0.00),
    ("Brother Cael", "Gregor", 0.40, 0.40, 0.45, 0.00, 0.00),
    ("Gregor", "Brother Cael", 0.45, 0.30, 0.50, 0.00, 0.00),
    ("Brother Cael", "Roland", 0.50, 0.50, 0.55, 0.00, 0.00),
    ("Roland", "Brother Cael", 0.55, 0.50, 0.60, 0.00, 0.00),

    # Marta and Elena — polite but Elena thinks Marta is naive
    ("Marta", "Elena",         0.30, 0.35, 0.25, 0.00, 0.00),
    ("Elena", "Marta",         0.35, 0.40, 0.30, 0.00, 0.00),

    # Marta and Roland — neutral/professional
    ("Marta", "Roland",        0.40, 0.35, 0.45, 0.00, 0.00),
    ("Roland", "Marta",        0.45, 0.40, 0.50, 0.00, 0.00),

    # Marta and Gregor — she fixed him up once
    ("Marta", "Gregor",        0.35, 0.30, 0.40, 0.00, 0.00),
    ("Gregor", "Marta",        0.50, 0.35, 0.55, 0.00, 0.00),

    # Aldric and Elena — guarded, Aldric senses she is too clever
    ("Aldric", "Elena",        0.10, 0.20, 0.15, 0.10, 0.00),
    ("Elena", "Aldric",        0.30, 0.25, 0.20, 0.00, 0.00),

    # Aldric and Roland — solid neighbors
    ("Aldric", "Roland",       0.50, 0.45, 0.55, 0.00, 0.00),
    ("Roland", "Aldric",       0.50, 0.40, 0.45, 0.00, 0.00),

    # Aldric and Gregor — trade food for tools regularly, decent respect
    ("Aldric", "Gregor",       0.45, 0.30, 0.55, 0.00, 0.00),
    ("Gregor", "Aldric",       0.45, 0.25, 0.50, 0.00, 0.00),
]


# ---------------------------------------------------------------------------
# Seeding logic
# ---------------------------------------------------------------------------


async def seed() -> None:
    engine = create_async_engine(settings.database_url, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        # Drop existing world with this name
        existing = await session.execute(
            select(World).where(World.name == WORLD_NAME)
        )
        existing_world = existing.scalar_one_or_none()
        if existing_world:
            await session.delete(existing_world)
            await session.commit()
            print(f"Dropped existing world '{WORLD_NAME}'")

        # Create world
        world = World(name=WORLD_NAME)
        session.add(world)
        await session.flush()  # get world.id

        # Create agents
        agent_map: dict[str, Agent] = {}
        for agent_data in AGENTS:
            inv = agent_data.pop("inventory")
            agent = Agent(world_id=world.id, **agent_data)
            session.add(agent)
            await session.flush()  # get agent.id

            for resource_type, quantity in inv.items():
                session.add(
                    AgentInventory(
                        agent_id=agent.id,
                        resource_type=resource_type,
                        quantity=quantity,
                    )
                )

            agent_map[agent.name] = agent
            agent_data["inventory"] = inv  # restore for idempotency

        await session.flush()

        # Create relationships
        for (src, tgt, trust, warmth, respect, resentment, fear) in RELATIONSHIPS:
            session.add(
                Relationship(
                    source_agent_id=agent_map[src].id,
                    target_agent_id=agent_map[tgt].id,
                    trust=trust,
                    warmth=warmth,
                    respect=respect,
                    resentment=resentment,
                    fear=fear,
                )
            )

        await session.commit()

    await engine.dispose()

    print(f"Seeded world '{WORLD_NAME}' with {len(AGENTS)} agents and {len(RELATIONSHIPS)} relationships.")
    print("Agent roster:")
    for a in AGENTS:
        print(f"  - {a['name']} ({a['profession'].value}, age {a['age']})")


if __name__ == "__main__":
    asyncio.run(seed())
