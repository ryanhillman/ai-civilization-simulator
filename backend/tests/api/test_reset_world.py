"""
Tests for SimulationService.reset_world — pure unit tests, no DB required.

Verifies:
- reset raises ValueError for missing world (delegates to _load_world)
- world ID is unchanged after reset (in-place, not delete+recreate)
- world state fields are set to the seeded baseline (turn=0, day=1, spring, clear)
- old agents are explicitly deleted from the session
- new agents are added matching the seed data count and names
- session.refresh is called so the returned world is not stale
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.domain.simulation_service import SimulationService
from app.enums import Season
from app.models.db import Agent, World
from app.seed_data import AGENTS, RELATIONSHIPS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_world(world_id: int = 1, name: str = "Ashenvale") -> MagicMock:
    w = MagicMock(spec=World)
    w.id = world_id
    w.name = name
    w.agents = []
    # Simulate a world that has been run for several turns
    w.current_turn = 7
    w.current_day = 14
    w.current_season = Season.summer
    w.weather = "stormy"
    return w


def _make_session() -> AsyncMock:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock())
    session.refresh = AsyncMock()
    # session.add and session.expire are synchronous in SQLAlchemy (not coroutines)
    session.add = MagicMock()
    session.expire = MagicMock()
    return session


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestResetWorldService:
    @pytest.mark.asyncio
    async def test_raises_if_world_not_found(self):
        svc = SimulationService()
        session = _make_session()
        with patch(
            "app.domain.simulation_service._load_world",
            side_effect=ValueError("World 99 not found"),
        ):
            with pytest.raises(ValueError, match="99"):
                await svc.reset_world(99, session)

    @pytest.mark.asyncio
    async def test_world_id_unchanged_after_reset(self):
        """The returned world must have the same ID — no delete+recreate."""
        mock_world = _mock_world(world_id=42)
        session = _make_session()
        with patch("app.domain.simulation_service._load_world", return_value=mock_world):
            result = await SimulationService().reset_world(42, session)
        assert result.id == 42

    @pytest.mark.asyncio
    async def test_world_state_reset_to_baseline(self):
        """After reset, world fields must match the seeded baseline."""
        mock_world = _mock_world()
        session = _make_session()
        with patch("app.domain.simulation_service._load_world", return_value=mock_world):
            await SimulationService().reset_world(1, session)
        assert mock_world.current_turn == 0
        assert mock_world.current_day == 1
        assert mock_world.current_season == Season.spring
        assert mock_world.weather == "clear"

    @pytest.mark.asyncio
    async def test_old_agents_deleted(self):
        """Every existing agent must be passed to session.delete."""
        agent_a = MagicMock(spec=Agent)
        agent_b = MagicMock(spec=Agent)
        mock_world = _mock_world()
        mock_world.agents = [agent_a, agent_b]
        session = _make_session()
        with patch("app.domain.simulation_service._load_world", return_value=mock_world):
            await SimulationService().reset_world(1, session)
        session.delete.assert_any_call(agent_a)
        session.delete.assert_any_call(agent_b)

    @pytest.mark.asyncio
    async def test_new_agents_added_matching_seed_count(self):
        """Exactly as many new Agent rows as AGENTS in seed_data must be added."""
        mock_world = _mock_world()
        session = _make_session()
        added_agents: list[Agent] = []

        def capture(obj):
            if isinstance(obj, Agent):
                added_agents.append(obj)

        session.add.side_effect = capture
        with patch("app.domain.simulation_service._load_world", return_value=mock_world):
            await SimulationService().reset_world(1, session)
        assert len(added_agents) == len(AGENTS)

    @pytest.mark.asyncio
    async def test_seeded_agent_names_match_seed_data(self):
        """The names of re-seeded agents must match AGENTS in seed_data exactly."""
        mock_world = _mock_world()
        session = _make_session()
        added_agents: list[Agent] = []

        def capture(obj):
            if isinstance(obj, Agent):
                added_agents.append(obj)

        session.add.side_effect = capture
        with patch("app.domain.simulation_service._load_world", return_value=mock_world):
            await SimulationService().reset_world(1, session)
        expected_names = {a["name"] for a in AGENTS}
        actual_names = {a.name for a in added_agents}
        assert actual_names == expected_names

    @pytest.mark.asyncio
    async def test_seeded_agents_have_correct_world_id(self):
        """All re-seeded agents must reference the original world ID."""
        mock_world = _mock_world(world_id=7)
        session = _make_session()
        added_agents: list[Agent] = []

        def capture(obj):
            if isinstance(obj, Agent):
                added_agents.append(obj)

        session.add.side_effect = capture
        with patch("app.domain.simulation_service._load_world", return_value=mock_world):
            await SimulationService().reset_world(7, session)
        for agent in added_agents:
            assert agent.world_id == 7

    @pytest.mark.asyncio
    async def test_session_flush_called_multiple_times(self):
        """flush() must be called at least twice (after deletes and after re-seeding)."""
        mock_world = _mock_world()
        session = _make_session()
        with patch("app.domain.simulation_service._load_world", return_value=mock_world):
            await SimulationService().reset_world(1, session)
        assert session.flush.call_count >= 2

    @pytest.mark.asyncio
    async def test_session_refresh_called_on_world(self):
        """session.refresh(world) must be called so the returned object is not stale."""
        mock_world = _mock_world()
        session = _make_session()
        with patch("app.domain.simulation_service._load_world", return_value=mock_world):
            await SimulationService().reset_world(1, session)
        session.refresh.assert_called_once_with(mock_world)

    @pytest.mark.asyncio
    async def test_turn_events_deleted_via_execute(self):
        """A DELETE statement for TurnEvents must be issued via session.execute."""
        mock_world = _mock_world()
        session = _make_session()
        with patch("app.domain.simulation_service._load_world", return_value=mock_world):
            await SimulationService().reset_world(1, session)
        # session.execute must have been called (at least once for TurnEvent delete)
        assert session.execute.call_count >= 1
