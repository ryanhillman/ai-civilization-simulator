"""
Village seed data — shared between the seed script and the reset endpoint.

Importing this module does NOT touch the database; it is pure Python data.
"""
from app.enums import Profession, ResourceType

WORLD_NAME = "Ashenvale"

# Each entry is a full agent definition including initial inventory.
# Keys match Agent ORM column names plus an "inventory" dict.
AGENTS: list[dict] = [
    {
        "name": "Aldric",
        "profession": Profession.farmer,
        "age": 42,
        "personality_traits": {
            "courage": 0.4, "greed": 0.2, "warmth": 0.8,
            "cunning": 0.2, "piety": 0.5,
        },
        "goals": [
            {"type": "produce", "target": "food", "priority": 1},
            {"type": "protect", "target": "family", "priority": 2},
        ],
        "inventory": {
            ResourceType.food: 18.0, ResourceType.coin: 5.0,
            ResourceType.wood: 8.0,  ResourceType.medicine: 1.0,
        },
    },
    {
        "name": "Marta",
        "profession": Profession.healer,
        "age": 35,
        "personality_traits": {
            "courage": 0.5, "greed": 0.1, "warmth": 0.9,
            "cunning": 0.4, "piety": 0.6,
        },
        "goals": [
            {"type": "heal",      "target": "villagers", "priority": 1},
            {"type": "stockpile", "target": "medicine",  "priority": 2},
        ],
        "inventory": {
            ResourceType.food: 10.0, ResourceType.coin: 12.0,
            ResourceType.wood: 4.0,  ResourceType.medicine: 15.0,
        },
    },
    {
        "name": "Gregor",
        "profession": Profession.blacksmith,
        "age": 51,
        "personality_traits": {
            "courage": 0.8, "greed": 0.3, "warmth": 0.3,
            "cunning": 0.4, "piety": 0.2,
        },
        "goals": [
            {"type": "produce",    "target": "tools", "priority": 1},
            {"type": "accumulate", "target": "coin",  "priority": 2},
        ],
        "inventory": {
            ResourceType.food: 8.0,  ResourceType.coin: 20.0,
            ResourceType.wood: 15.0, ResourceType.medicine: 0.0,
        },
    },
    {
        "name": "Elena",
        "profession": Profession.merchant,
        "age": 29,
        "personality_traits": {
            "courage": 0.4, "greed": 0.7, "warmth": 0.4,
            "cunning": 0.9, "piety": 0.1,
        },
        "goals": [
            {"type": "trade",      "target": "profit", "priority": 1},
            {"type": "accumulate", "target": "coin",   "priority": 2},
        ],
        "inventory": {
            ResourceType.food: 12.0, ResourceType.coin: 35.0,
            ResourceType.wood: 6.0,  ResourceType.medicine: 3.0,
        },
    },
    {
        "name": "Brother Cael",
        "profession": Profession.priest,
        "age": 58,
        "personality_traits": {
            "courage": 0.5, "greed": 0.05, "warmth": 0.85,
            "cunning": 0.3, "piety": 0.99,
        },
        "goals": [
            {"type": "maintain", "target": "harmony", "priority": 1},
            {"type": "tend",     "target": "shrine",  "priority": 2},
        ],
        "inventory": {
            ResourceType.food: 9.0, ResourceType.coin: 8.0,
            ResourceType.wood: 5.0, ResourceType.medicine: 4.0,
        },
    },
    {
        "name": "Roland",
        "profession": Profession.soldier,
        "age": 33,
        "personality_traits": {
            "courage": 0.9, "greed": 0.3, "warmth": 0.4,
            "cunning": 0.5, "piety": 0.3,
        },
        "goals": [
            {"type": "protect", "target": "village", "priority": 1},
            {"type": "earn",    "target": "coin",    "priority": 2},
        ],
        "inventory": {
            ResourceType.food: 10.0, ResourceType.coin: 15.0,
            ResourceType.wood: 3.0,  ResourceType.medicine: 2.0,
        },
    },
]

# Directed relationship seeds.
# (source_name, target_name, trust, warmth, respect, resentment, fear)
RELATIONSHIPS: list[tuple] = [
    ("Aldric",       "Marta",        0.75,  0.70, 0.60, 0.00, 0.00),
    ("Marta",        "Aldric",       0.65,  0.60, 0.50, 0.00, 0.00),
    ("Aldric",       "Brother Cael", 0.60,  0.65, 0.70, 0.00, 0.00),
    ("Brother Cael", "Aldric",       0.60,  0.55, 0.55, 0.00, 0.00),
    ("Gregor",       "Roland",       0.50,  0.40, 0.70, 0.00, 0.00),
    ("Roland",       "Gregor",       0.50,  0.45, 0.65, 0.00, 0.00),
    ("Gregor",       "Elena",       -0.30, -0.10, 0.10, 0.40, 0.00),
    ("Elena",        "Gregor",       0.10,  0.20, 0.40, 0.00, 0.10),
    ("Roland",       "Elena",       -0.20, -0.10, 0.10, 0.55, 0.00),
    ("Elena",        "Roland",       0.30,  0.20, 0.30, 0.00, 0.15),
    ("Brother Cael", "Marta",        0.60,  0.65, 0.55, 0.00, 0.00),
    ("Marta",        "Brother Cael", 0.65,  0.70, 0.65, 0.00, 0.00),
    ("Brother Cael", "Elena",        0.30,  0.35, 0.20, 0.00, 0.00),
    ("Elena",        "Brother Cael", 0.45,  0.30, 0.50, 0.00, 0.00),
    ("Brother Cael", "Gregor",       0.40,  0.40, 0.45, 0.00, 0.00),
    ("Gregor",       "Brother Cael", 0.45,  0.30, 0.50, 0.00, 0.00),
    ("Brother Cael", "Roland",       0.50,  0.50, 0.55, 0.00, 0.00),
    ("Roland",       "Brother Cael", 0.55,  0.50, 0.60, 0.00, 0.00),
    ("Marta",        "Elena",        0.30,  0.35, 0.25, 0.00, 0.00),
    ("Elena",        "Marta",        0.35,  0.40, 0.30, 0.00, 0.00),
    ("Marta",        "Roland",       0.40,  0.35, 0.45, 0.00, 0.00),
    ("Roland",       "Marta",        0.45,  0.40, 0.50, 0.00, 0.00),
    ("Marta",        "Gregor",       0.35,  0.30, 0.40, 0.00, 0.00),
    ("Gregor",       "Marta",        0.50,  0.35, 0.55, 0.00, 0.00),
    ("Aldric",       "Elena",        0.10,  0.20, 0.15, 0.10, 0.00),
    ("Elena",        "Aldric",       0.30,  0.25, 0.20, 0.00, 0.00),
    ("Aldric",       "Roland",       0.50,  0.45, 0.55, 0.00, 0.00),
    ("Roland",       "Aldric",       0.50,  0.40, 0.45, 0.00, 0.00),
    ("Aldric",       "Gregor",       0.45,  0.30, 0.55, 0.00, 0.00),
    ("Gregor",       "Aldric",       0.45,  0.25, 0.50, 0.00, 0.00),
]
