"""Tests for Stage 2: agent_refresh — hunger, starvation, sickness effects."""
import pytest

from app.models.db import Profession
from app.simulation.stages.agent_refresh import (
    HUNGER_INCREASE_PER_TURN,
    SICKNESS_HUNGER_MULTIPLIER,
    refresh_agent,
    refresh_agents,
)
from app.simulation.types import InventorySnapshot, TurnContext

from tests.simulation.conftest import make_agent_state, make_world_state


class TestRefreshAgent:
    # ------------------------------------------------------------------
    # Well-fed agent
    # ------------------------------------------------------------------

    def test_hunger_decreases_when_well_fed(self):
        agent = make_agent_state(hunger=0.5, food=10.0, profession=Profession.farmer)
        result = refresh_agent(agent)
        assert result.hunger < agent.hunger

    def test_food_consumed_from_inventory(self):
        agent = make_agent_state(food=10.0, profession=Profession.farmer)
        result = refresh_agent(agent)
        # farmer consumes 0.8 per turn
        assert result.inventory.food == pytest.approx(10.0 - 0.8, abs=0.01)

    def test_hunger_floored_at_zero(self):
        # Agent was already at zero hunger — should not go negative
        agent = make_agent_state(hunger=0.0, food=10.0, profession=Profession.farmer)
        result = refresh_agent(agent)
        assert result.hunger >= 0.0

    # ------------------------------------------------------------------
    # Starving agent
    # ------------------------------------------------------------------

    def test_hunger_increases_with_no_food(self):
        agent = make_agent_state(hunger=0.0, food=0.0, profession=Profession.farmer)
        result = refresh_agent(agent)
        assert result.hunger > 0.0

    def test_hunger_increase_bounded_by_constant(self):
        agent = make_agent_state(hunger=0.0, food=0.0, profession=Profession.farmer)
        result = refresh_agent(agent)
        assert result.hunger <= HUNGER_INCREASE_PER_TURN

    def test_agent_dies_when_hunger_reaches_one(self):
        # Hunger just below threshold — one more turn with no food kills
        agent = make_agent_state(hunger=0.9, food=0.0, profession=Profession.farmer)
        result = refresh_agent(agent)
        assert result.hunger >= 1.0
        assert result.is_alive is False

    def test_agent_stays_alive_below_one(self):
        agent = make_agent_state(hunger=0.5, food=5.0, profession=Profession.farmer)
        result = refresh_agent(agent)
        assert result.is_alive is True

    def test_food_inventory_reaches_zero_not_negative(self):
        agent = make_agent_state(food=0.3, profession=Profession.farmer)
        result = refresh_agent(agent)
        assert result.inventory.food >= 0.0

    # ------------------------------------------------------------------
    # Sickness
    # ------------------------------------------------------------------

    def test_sick_agent_consumes_more_food(self):
        healthy = make_agent_state(food=10.0, is_sick=False, profession=Profession.farmer)
        sick = make_agent_state(food=10.0, is_sick=True, profession=Profession.farmer)
        healthy_result = refresh_agent(healthy)
        sick_result = refresh_agent(sick)
        # Sick agent should have less food remaining
        assert sick_result.inventory.food < healthy_result.inventory.food

    def test_sick_agent_hunger_rises_faster_without_food(self):
        healthy = make_agent_state(food=0.0, hunger=0.0, is_sick=False, profession=Profession.farmer)
        sick = make_agent_state(food=0.0, hunger=0.0, is_sick=True, profession=Profession.farmer)
        healthy_result = refresh_agent(healthy)
        sick_result = refresh_agent(sick)
        assert sick_result.hunger >= healthy_result.hunger

    # ------------------------------------------------------------------
    # Dead agents are skipped
    # ------------------------------------------------------------------

    def test_dead_agent_is_not_modified(self):
        agent = make_agent_state(is_alive=False, hunger=0.5, food=5.0)
        result = refresh_agent(agent)
        assert result.hunger == agent.hunger
        assert result.inventory.food == agent.inventory.food

    # ------------------------------------------------------------------
    # Profession-specific consumption rates
    # ------------------------------------------------------------------

    def test_soldier_consumes_more_than_priest(self):
        soldier = make_agent_state(food=10.0, profession=Profession.soldier)
        priest = make_agent_state(food=10.0, profession=Profession.priest)
        soldier_result = refresh_agent(soldier)
        priest_result = refresh_agent(priest)
        assert soldier_result.inventory.food < priest_result.inventory.food

    # ------------------------------------------------------------------
    # refresh_agents (stage entry point)
    # ------------------------------------------------------------------

    def test_refresh_agents_updates_all(self):
        a1 = make_agent_state(agent_id=1, food=0.0, hunger=0.0)
        a2 = make_agent_state(agent_id=2, food=10.0, hunger=0.5)
        world = make_world_state(agents=[a1, a2])
        ctx = TurnContext(world_state=world)
        result_ctx = refresh_agents(ctx)
        updated = {a.id: a for a in result_ctx.world_state.agents}
        assert updated[1].hunger > 0.0   # starving: hunger rose
        assert updated[2].hunger < 0.5   # well-fed: hunger fell

    def test_refresh_agents_does_not_mutate_input(self):
        agent = make_agent_state(agent_id=1, food=5.0)
        world = make_world_state(agents=[agent])
        original_food = world.agents[0].inventory.food
        ctx = TurnContext(world_state=world)
        refresh_agents(ctx)
        assert world.agents[0].inventory.food == original_food
