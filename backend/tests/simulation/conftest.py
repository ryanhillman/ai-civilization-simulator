"""
Shared fixtures for simulation engine tests.

All fixtures are pure domain objects — no DB, no SQLAlchemy.
"""
import pytest

from app.models.db import Profession, Season
from app.simulation.types import AgentState, InventorySnapshot, WorldState


def make_agent_state(
    agent_id: int = 1,
    world_id: int = 1,
    name: str = "Test",
    profession: Profession = Profession.farmer,
    age: int = 30,
    is_alive: bool = True,
    is_sick: bool = False,
    hunger: float = 0.0,
    food: float = 10.0,
    coin: float = 5.0,
    wood: float = 5.0,
    medicine: float = 2.0,
    goals: list | None = None,
    traits: dict | None = None,
) -> AgentState:
    return AgentState(
        id=agent_id,
        world_id=world_id,
        name=name,
        profession=profession,
        age=age,
        is_alive=is_alive,
        is_sick=is_sick,
        hunger=hunger,
        personality_traits=traits or {"courage": 0.5, "greed": 0.3, "warmth": 0.5, "cunning": 0.5, "piety": 0.3},
        goals=goals or [],
        inventory=InventorySnapshot(food=food, coin=coin, wood=wood, medicine=medicine),
    )


def make_world_state(
    world_id: int = 1,
    turn: int = 0,
    day: int = 1,
    season: Season = Season.spring,
    weather: str = "clear",
    agents: list[AgentState] | None = None,
) -> WorldState:
    return WorldState(
        id=world_id,
        name="TestVillage",
        current_turn=turn,
        current_day=day,
        current_season=season,
        weather=weather,
        agents=agents or [],
    )


@pytest.fixture
def farmer() -> AgentState:
    return make_agent_state(
        agent_id=1,
        profession=Profession.farmer,
        goals=[{"type": "produce", "target": "food", "priority": 1}],
        traits={"courage": 0.4, "greed": 0.2, "warmth": 0.8, "cunning": 0.2, "piety": 0.5},
    )


@pytest.fixture
def healer() -> AgentState:
    return make_agent_state(
        agent_id=2,
        name="Healer",
        profession=Profession.healer,
        goals=[{"type": "heal", "target": "villagers", "priority": 1}],
        medicine=15.0,
    )


@pytest.fixture
def merchant() -> AgentState:
    return make_agent_state(
        agent_id=3,
        name="Merchant",
        profession=Profession.merchant,
        goals=[{"type": "trade", "target": "profit", "priority": 1}],
        traits={"courage": 0.4, "greed": 0.7, "warmth": 0.4, "cunning": 0.9, "piety": 0.1},
    )


@pytest.fixture
def blacksmith() -> AgentState:
    return make_agent_state(
        agent_id=4,
        name="Blacksmith",
        profession=Profession.blacksmith,
        goals=[{"type": "produce", "target": "tools", "priority": 1}],
        wood=15.0,
    )


@pytest.fixture
def village(farmer, healer, merchant, blacksmith) -> WorldState:
    return make_world_state(agents=[farmer, healer, merchant, blacksmith])
