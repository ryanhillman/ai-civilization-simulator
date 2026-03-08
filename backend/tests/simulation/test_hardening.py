"""
Phase 2 hardening tests — five architectural concerns.

Concern 1  Simulation type independence
           app.simulation.* must not import from app.models.db.
           Only app.enums (plain Python enums, no ORM) is permitted.

Concern 2  Thin SimulationService
           app.domain.simulation_service must contain only field-mapping /
           translation logic. Simulation rules belong in app.simulation.

Concern 3  Deterministic action tie-breaking
           Equal-priority goals resolve by original list order, every run.

Concern 4  Deterministic TurnResult.summary
           build_turn_summary() is a pure function: same events → same text.

Concern 5  Stable TurnResult contract
           The API/frontend contract (field names, JSON shape) must not leak
           internal pipeline-stage details.
"""
from __future__ import annotations

import ast
import json
import pathlib
from types import SimpleNamespace

import pytest

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_BACKEND = pathlib.Path(__file__).parent.parent.parent  # …/backend/
_APP = _BACKEND / "app"

_SIMULATION_FILES = [
    _APP / "simulation" / "types.py",
    _APP / "simulation" / "pipeline.py",
    _APP / "simulation" / "runner.py",
    _APP / "simulation" / "stages" / "world_advance.py",
    _APP / "simulation" / "stages" / "agent_refresh.py",
    _APP / "simulation" / "stages" / "opportunity_gen.py",
    _APP / "simulation" / "stages" / "action_resolve.py",
    _APP / "simulation" / "stages" / "event_hooks.py",
    _APP / "simulation" / "stages" / "memory_hooks.py",
]


def _static_imports(path: pathlib.Path) -> list[str]:
    """Return every module name imported at the top level of *path*."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                modules.append(alias.name)
    return modules


# ---------------------------------------------------------------------------
# Concern 1 — Simulation type independence
# ---------------------------------------------------------------------------


class TestSimulationTypeIndependence:
    """
    Boundary: app.simulation.* → app.enums  ✓
              app.simulation.* → app.models.db  ✗ (would load SQLAlchemy ORM)
    """

    def test_simulation_types_does_not_import_app_models_db(self):
        """Regression guard for the most critical file: types.py."""
        imports = _static_imports(_APP / "simulation" / "types.py")
        assert "app.models.db" not in imports, (
            "app.simulation.types imports from app.models.db — "
            "shared enums must live in app.enums"
        )

    @pytest.mark.parametrize("path", _SIMULATION_FILES, ids=lambda p: p.name)
    def test_simulation_file_does_not_import_app_models_db(self, path: pathlib.Path):
        """No file inside app.simulation may import from app.models.db."""
        imports = _static_imports(path)
        assert "app.models.db" not in imports, (
            f"{path.relative_to(_BACKEND)} imports from app.models.db — "
            f"use app.enums for shared enums"
        )

    def test_no_orm_class_in_simulation_types_namespace(self):
        """No SQLAlchemy ORM model (carrying __tablename__) leaks into types.py."""
        import inspect
        import app.simulation.types as sim_types

        for name, obj in vars(sim_types).items():
            if inspect.isclass(obj) and hasattr(obj, "__tablename__"):
                pytest.fail(
                    f"ORM model '{name}' (table='{obj.__tablename__}') "
                    f"found in app.simulation.types namespace"
                )

    def test_shared_enums_importable_from_app_enums(self):
        """Canonical enum location is app.enums."""
        from app.enums import EventType, Profession, ResourceType, Season

        assert Profession.farmer.value == "farmer"
        assert Season.winter.value == "winter"
        assert ResourceType.food.value == "food"
        assert EventType.harvest.value == "harvest"

    def test_shared_enums_still_importable_from_app_models_db(self):
        """Backward-compat: enums remain importable from app.models.db."""
        from app.models.db import EventType, Profession, ResourceType, Season

        assert Profession.blacksmith.value == "blacksmith"

    def test_app_enums_has_no_sqlalchemy_dependency(self):
        """app.enums must not import sqlalchemy at all."""
        imports = _static_imports(_APP / "enums.py")
        for mod in imports:
            assert not mod.startswith("sqlalchemy"), (
                f"app.enums imports '{mod}' — it must be pure Python only"
            )


# ---------------------------------------------------------------------------
# Concern 2 — Thin SimulationService
# ---------------------------------------------------------------------------


def _mock_inv_item(resource_type, quantity: float):
    return SimpleNamespace(resource_type=resource_type, quantity=quantity)


def _mock_agent(**overrides):
    from app.enums import Profession

    base = dict(
        id=1,
        world_id=1,
        name="Test",
        profession=Profession.farmer,
        age=30,
        is_alive=True,
        is_sick=False,
        hunger=0.0,
        personality_traits={"warmth": 0.5},
        goals=[],
        inventory=[],
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _mock_world(**overrides):
    from app.enums import Season

    base = dict(
        id=1,
        name="TestVillage",
        current_turn=0,
        current_day=1,
        current_season=Season.spring,
        weather="clear",
        agents=[],
    )
    base.update(overrides)
    return SimpleNamespace(**base)


class TestThinSimulationService:
    """
    SimulationService responsibilities:
      ✓ Load DB records → produce domain objects  (agent_to_state, world_to_state)
      ✓ Take domain objects → produce DB records  (build_turn_event, build_memory)
      ✓ Invoke TurnRunner                         (advance_turn stub)
      ✗ Must NOT contain hunger thresholds, food rates, action maps, or any
        other simulation rule — those belong in app.simulation.
    """

    def test_agent_to_state_maps_scalar_fields(self):
        from app.domain.simulation_service import agent_to_state
        from app.enums import Profession

        mock = _mock_agent(id=7, name="Alice", profession=Profession.merchant,
                           age=29, is_alive=True, is_sick=True, hunger=0.4)
        result = agent_to_state(mock)

        assert result.id == 7
        assert result.name == "Alice"
        assert result.profession == Profession.merchant
        assert result.age == 29
        assert result.is_alive is True
        assert result.is_sick is True
        assert result.hunger == pytest.approx(0.4)

    def test_agent_to_state_maps_inventory(self):
        from app.domain.simulation_service import agent_to_state
        from app.enums import ResourceType

        inv = [
            _mock_inv_item(ResourceType.food, 8.0),
            _mock_inv_item(ResourceType.coin, 12.0),
            _mock_inv_item(ResourceType.medicine, 3.0),
        ]
        mock = _mock_agent(inventory=inv)
        result = agent_to_state(mock)

        assert result.inventory.food == pytest.approx(8.0)
        assert result.inventory.coin == pytest.approx(12.0)
        assert result.inventory.medicine == pytest.approx(3.0)
        assert result.inventory.wood == pytest.approx(0.0)

    def test_agent_to_state_empty_inventory_is_zeroes(self):
        from app.domain.simulation_service import agent_to_state

        result = agent_to_state(_mock_agent(inventory=[]))
        assert result.inventory.food == 0.0
        assert result.inventory.coin == 0.0

    def test_agent_to_state_none_goals_and_traits_become_empty(self):
        from app.domain.simulation_service import agent_to_state

        mock = _mock_agent(personality_traits=None, goals=None)
        result = agent_to_state(mock)
        assert result.personality_traits == {}
        assert result.goals == []

    def test_world_to_state_maps_scalar_fields(self):
        from app.domain.simulation_service import world_to_state
        from app.enums import Season

        mock = _mock_world(id=99, name="Ashenvale", current_turn=5,
                           current_day=15, current_season=Season.autumn,
                           weather="foggy", agents=[])
        result = world_to_state(mock)

        assert result.id == 99
        assert result.name == "Ashenvale"
        assert result.current_turn == 5
        assert result.current_day == 15
        assert result.current_season == Season.autumn
        assert result.weather == "foggy"

    def test_world_to_state_converts_all_agents(self):
        from app.domain.simulation_service import world_to_state

        agents = [_mock_agent(id=1), _mock_agent(id=2), _mock_agent(id=3)]
        mock = _mock_world(agents=agents)
        result = world_to_state(mock)

        assert len(result.agents) == 3
        assert {a.id for a in result.agents} == {1, 2, 3}

    def test_build_turn_event_maps_all_fields(self):
        from app.domain.simulation_service import build_turn_event
        from app.simulation.types import TurnEventRecord
        from app.enums import EventType

        record = TurnEventRecord(
            world_id=3, turn_number=7, event_type=EventType.harvest,
            description="Agent 1 harvested 3.4 food.",
            agent_ids=[1, 2],
            details={"food_gained": 3.4},
        )
        orm = build_turn_event(record)

        assert orm.world_id == 3
        assert orm.turn_number == 7
        assert orm.event_type == EventType.harvest
        assert orm.description == record.description
        assert orm.agent_ids == [1, 2]
        assert orm.details == {"food_gained": 3.4}

    def test_build_memory_maps_all_fields(self):
        from app.domain.simulation_service import build_memory
        from app.simulation.types import MemoryRecord
        from app.enums import EventType

        record = MemoryRecord(
            agent_id=1, world_id=2, turn_number=5,
            event_type=EventType.sickness,
            summary="Fell ill during the harvest.",
            emotional_weight=-0.4,
            related_agent_id=3,
        )
        orm = build_memory(record)

        assert orm.agent_id == 1
        assert orm.world_id == 2
        assert orm.turn_number == 5
        assert orm.event_type == EventType.sickness
        assert orm.summary == record.summary
        assert orm.emotional_weight == pytest.approx(-0.4)
        assert orm.related_agent_id == 3

    def test_simulation_service_contains_no_simulation_rules(self):
        """
        Static guard: simulation_service.py must not define simulation rules.
        If any of these identifiers appear there, a rule has leaked from the engine.
        """
        source = (_APP / "domain" / "simulation_service.py").read_text(encoding="utf-8")
        forbidden = [
            "FOOD_CONSUMPTION",
            "HUNGER_INCREASE",
            "_GOAL_ACTION_MAP",
            "harvest_food",
            "DAYS_PER_SEASON",
            "MEMORY_THRESHOLD",
        ]
        for token in forbidden:
            assert token not in source, (
                f"simulation_service.py contains '{token}', which is a "
                f"simulation rule — move it to app.simulation"
            )


# ---------------------------------------------------------------------------
# Concern 3 — Deterministic action tie-breaking
# ---------------------------------------------------------------------------


class TestDeterministicActionTieBreaking:
    """
    Tie-break rule (documented in _select_action):
    When two goals share the same priority value, the goal appearing
    earlier in the agent's goals list wins. This is enforced by the
    explicit (priority, original_index) sort key — not by relying on
    Python's stable-sort side effect.
    """

    def test_equal_priority_first_goal_wins(self):
        """Goals at equal priority: index 0 beats index 1."""
        from app.simulation.stages.action_resolve import _select_action
        from app.simulation.types import Opportunity
        from app.enums import Profession
        from tests.simulation.conftest import make_agent_state

        agent = make_agent_state(
            agent_id=1,
            profession=Profession.farmer,
            goals=[
                {"type": "produce", "priority": 1},  # index 0 → harvest_food
                {"type": "trade",   "priority": 1},  # index 1 → trade_goods
            ],
        )
        opps = [
            Opportunity(agent_id=1, action_type="harvest_food"),
            Opportunity(agent_id=1, action_type="trade_goods",
                        metadata={"coin_gain_base": 3.0}),
            Opportunity(agent_id=1, action_type="rest"),
        ]
        assert _select_action(agent, opps).action_type == "harvest_food"

    def test_equal_priority_second_goal_wins_when_first_unavailable(self):
        """If index-0 goal has no matching opportunity, index-1 goal is tried."""
        from app.simulation.stages.action_resolve import _select_action
        from app.simulation.types import Opportunity
        from app.enums import Profession
        from tests.simulation.conftest import make_agent_state

        agent = make_agent_state(
            agent_id=1,
            profession=Profession.farmer,
            goals=[
                {"type": "produce", "priority": 1},   # harvest_food — NOT in opps
                {"type": "trade",   "priority": 1},   # trade_goods  — IS in opps
            ],
        )
        opps = [
            Opportunity(agent_id=1, action_type="trade_goods",
                        metadata={"coin_gain_base": 3.0}),
            Opportunity(agent_id=1, action_type="rest"),
        ]
        assert _select_action(agent, opps).action_type == "trade_goods"

    def test_swapping_equal_priority_goals_changes_selection(self):
        """Tie-break is positional: reversing the goals list reverses the choice."""
        from app.simulation.stages.action_resolve import _select_action
        from app.simulation.types import Opportunity
        from app.enums import Profession
        from tests.simulation.conftest import make_agent_state

        opps = [
            Opportunity(agent_id=1, action_type="harvest_food"),
            Opportunity(agent_id=1, action_type="trade_goods",
                        metadata={"coin_gain_base": 3.0}),
            Opportunity(agent_id=1, action_type="rest"),
        ]

        agent_produce_first = make_agent_state(
            agent_id=1, profession=Profession.farmer,
            goals=[
                {"type": "produce", "priority": 1},
                {"type": "trade",   "priority": 1},
            ],
        )
        agent_trade_first = make_agent_state(
            agent_id=1, profession=Profession.farmer,
            goals=[
                {"type": "trade",   "priority": 1},
                {"type": "produce", "priority": 1},
            ],
        )

        r1 = _select_action(agent_produce_first, opps).action_type
        r2 = _select_action(agent_trade_first,   opps).action_type

        assert r1 == "harvest_food"
        assert r2 == "trade_goods"
        assert r1 != r2

    def test_action_selection_identical_on_repeated_calls(self):
        """_select_action must return the same result for identical inputs, always."""
        from app.simulation.stages.action_resolve import _select_action
        from app.simulation.types import Opportunity
        from app.enums import Profession
        from tests.simulation.conftest import make_agent_state

        agent = make_agent_state(
            agent_id=1, profession=Profession.farmer,
            goals=[{"type": "produce", "priority": 1}],
        )
        opps = [
            Opportunity(agent_id=1, action_type="harvest_food"),
            Opportunity(agent_id=1, action_type="rest"),
        ]
        results = {_select_action(agent, opps).action_type for _ in range(20)}
        assert results == {"harvest_food"}, "action selection is non-deterministic"

    def test_full_turn_resolved_actions_identical_across_runs(self):
        """Running the same WorldState twice must yield byte-identical actions."""
        from app.simulation.runner import TurnRunner
        from app.enums import Profession
        from tests.simulation.conftest import make_agent_state, make_world_state

        world = make_world_state(agents=[
            make_agent_state(agent_id=1, profession=Profession.farmer,
                             goals=[{"type": "produce", "priority": 1}],
                             traits={"warmth": 0.8, "courage": 0.4,
                                     "greed": 0.2, "cunning": 0.2, "piety": 0.5},
                             food=10.0),
            make_agent_state(agent_id=2, profession=Profession.merchant,
                             goals=[{"type": "trade", "priority": 1}],
                             traits={"courage": 0.4, "greed": 0.7,
                                     "warmth": 0.4, "cunning": 0.9, "piety": 0.1},
                             coin=20.0),
        ])
        runner = TurnRunner()
        r1 = runner.run_turn(world)
        r2 = runner.run_turn(world)

        sig = lambda r: [(a.agent_id, a.action_type, a.outcome, a.details)
                         for a in r.resolved_actions]
        assert sig(r1) == sig(r2)

    def test_priority_ordering_lower_number_wins(self):
        """Priority 1 beats priority 2, regardless of list position."""
        from app.simulation.stages.action_resolve import _select_action
        from app.simulation.types import Opportunity
        from app.enums import Profession
        from tests.simulation.conftest import make_agent_state

        agent = make_agent_state(
            agent_id=1, profession=Profession.farmer,
            goals=[
                {"type": "trade",   "priority": 2},  # lower priority
                {"type": "produce", "priority": 1},  # higher priority — appears second
            ],
        )
        opps = [
            Opportunity(agent_id=1, action_type="harvest_food"),
            Opportunity(agent_id=1, action_type="trade_goods",
                        metadata={"coin_gain_base": 3.0}),
            Opportunity(agent_id=1, action_type="rest"),
        ]
        # Priority 1 ("produce") wins even though it's index 1 in the goals list
        assert _select_action(agent, opps).action_type == "harvest_food"


# ---------------------------------------------------------------------------
# Concern 4 — Deterministic TurnResult.summary
# ---------------------------------------------------------------------------


class TestDeterministicTurnResultSummary:
    """
    build_turn_summary() is a pure function at module level in app.simulation.runner.
    Same input → same output, every call, no randomness, no LLM.
    """

    def test_empty_events_returns_fixed_quiet_message(self):
        from app.simulation.runner import build_turn_summary

        assert build_turn_summary([]) == "A quiet turn passed in the village."

    def test_single_event_returns_its_description(self):
        from app.simulation.runner import build_turn_summary
        from app.simulation.types import TurnEventRecord
        from app.enums import EventType

        events = [TurnEventRecord(world_id=1, turn_number=1,
                                  event_type=EventType.harvest,
                                  description="Agent 1 harvested 3.4 food.",
                                  agent_ids=[1])]
        assert build_turn_summary(events) == "Agent 1 harvested 3.4 food."

    def test_five_events_joined_with_spaces(self):
        from app.simulation.runner import build_turn_summary
        from app.simulation.types import TurnEventRecord
        from app.enums import EventType

        events = [
            TurnEventRecord(world_id=1, turn_number=1, event_type=EventType.harvest,
                            description=f"Event {i}.", agent_ids=[i])
            for i in range(5)
        ]
        result = build_turn_summary(events)
        for i in range(5):
            assert f"Event {i}." in result
        assert "more events" not in result

    def test_more_than_five_events_shows_overflow_count(self):
        from app.simulation.runner import build_turn_summary
        from app.simulation.types import TurnEventRecord
        from app.enums import EventType

        events = [
            TurnEventRecord(world_id=1, turn_number=1, event_type=EventType.rest,
                            description=f"Event {i}.", agent_ids=[i])
            for i in range(8)
        ]
        result = build_turn_summary(events)
        assert "and 3 more events." in result

    def test_summary_is_deterministic_repeated_calls(self):
        from app.simulation.runner import build_turn_summary
        from app.simulation.types import TurnEventRecord
        from app.enums import EventType

        events = [
            TurnEventRecord(world_id=1, turn_number=1, event_type=EventType.harvest,
                            description="Agent 1 harvested 3.4 food.", agent_ids=[1]),
            TurnEventRecord(world_id=1, turn_number=1, event_type=EventType.trade,
                            description="Agent 2 traded goods for 5.7 coin.", agent_ids=[2]),
        ]
        results = {build_turn_summary(events) for _ in range(10)}
        assert len(results) == 1, "build_turn_summary is non-deterministic"

    def test_full_turn_summary_identical_across_runs(self):
        """TurnResult.summary must be equal when running the same world twice."""
        from app.simulation.runner import TurnRunner
        from app.enums import Profession
        from tests.simulation.conftest import make_agent_state, make_world_state

        agent = make_agent_state(
            agent_id=1, profession=Profession.farmer,
            goals=[{"type": "produce", "priority": 1}],
            traits={"warmth": 0.8, "courage": 0.4,
                    "greed": 0.2, "cunning": 0.2, "piety": 0.5},
            food=10.0,
        )
        world = make_world_state(agents=[agent])
        runner = TurnRunner()
        assert runner.run_turn(world).summary == runner.run_turn(world).summary

    def test_summary_contains_marker_from_event_description(self):
        """Summary text is derived from event descriptions, not invented."""
        from app.simulation.runner import build_turn_summary
        from app.simulation.types import TurnEventRecord
        from app.enums import EventType

        events = [TurnEventRecord(world_id=1, turn_number=1,
                                  event_type=EventType.harvest,
                                  description="UNIQUE_SENTINEL_XYZ_42",
                                  agent_ids=[1])]
        assert "UNIQUE_SENTINEL_XYZ_42" in build_turn_summary(events)


# ---------------------------------------------------------------------------
# Concern 5 — Stable TurnResult contract
# ---------------------------------------------------------------------------


class TestStableTurnResultContract:
    """
    The API/frontend contract is TurnResult. Tests here enforce:
    - required fields are present and named correctly
    - no internal pipeline-stage names bleed into the response
    - the JSON serialisation round-trips cleanly
    - the WorldState sub-object carries the fields the frontend expects
    - two runs of the same world produce structurally identical results

    Note on frontend divergence
    ---------------------------
    frontend/src/types/index.ts defines TurnResult as
        { world: World; events: TurnEvent[]; turn_number: number }
    which is the *planned API response DTO shape*, not the domain object.
    The API route handler (Phase 3) will translate the domain TurnResult
    to that DTO. The tests below protect the domain contract; a separate
    schema test will be added when the route is implemented.
    """

    _REQUIRED_FIELDS = {
        "world_id",
        "turn_number",
        "world_state",
        "resolved_actions",
        "events",
        "memories",
        "summary",
    }

    _PIPELINE_STAGE_NAMES = {
        "advance_world",
        "refresh_agents",
        "generate_opportunities",
        "resolve_actions",
        "create_turn_events",
        "record_memories",
    }

    def test_turn_result_has_all_required_fields(self):
        from app.simulation.types import TurnResult

        missing = self._REQUIRED_FIELDS - set(TurnResult.model_fields)
        assert not missing, f"TurnResult is missing contract fields: {missing}"

    def test_turn_result_does_not_expose_pipeline_stage_names(self):
        """Internal stage names must not appear as fields in TurnResult."""
        from app.simulation.types import TurnResult

        leaked = self._PIPELINE_STAGE_NAMES & set(TurnResult.model_fields)
        assert not leaked, (
            f"Internal pipeline stage name(s) leaked into TurnResult fields: {leaked}"
        )

    def test_world_state_has_frontend_expected_fields(self):
        """WorldState must carry the fields the frontend World interface maps to."""
        from app.simulation.types import WorldState

        expected = {
            "id", "name", "current_turn", "current_day",
            "current_season", "weather", "agents",
        }
        missing = expected - set(WorldState.model_fields)
        assert not missing, f"WorldState missing frontend-expected fields: {missing}"

    def test_turn_event_record_has_frontend_expected_fields(self):
        """TurnEventRecord must carry the fields the frontend TurnEvent interface maps to."""
        from app.simulation.types import TurnEventRecord

        expected = {
            "world_id", "turn_number", "event_type",
            "description", "agent_ids", "details",
        }
        missing = expected - set(TurnEventRecord.model_fields)
        assert not missing, (
            f"TurnEventRecord missing frontend-expected fields: {missing}"
        )

    def test_turn_result_json_round_trips_cleanly(self):
        """A real TurnResult must serialise and deserialise without error or data loss."""
        from app.simulation.runner import TurnRunner
        from app.simulation.types import TurnResult
        from app.enums import Profession
        from tests.simulation.conftest import make_agent_state, make_world_state

        agent = make_agent_state(
            agent_id=1, profession=Profession.farmer,
            goals=[{"type": "produce", "priority": 1}],
            traits={"warmth": 0.8, "courage": 0.4,
                    "greed": 0.2, "cunning": 0.2, "piety": 0.5},
            food=10.0,
        )
        result = TurnRunner().run_turn(make_world_state(agents=[agent]))

        payload = json.loads(result.model_dump_json())

        assert payload["turn_number"] == result.turn_number
        assert payload["world_id"] == result.world_id
        assert isinstance(payload["events"], list)
        assert isinstance(payload["memories"], list)
        assert isinstance(payload["resolved_actions"], list)
        assert isinstance(payload["summary"], str)
        assert "world_state" in payload

    def test_turn_result_structure_identical_across_runs(self):
        """Two runs of the same WorldState must produce the same field structure."""
        from app.simulation.runner import TurnRunner
        from app.enums import Profession
        from tests.simulation.conftest import make_agent_state, make_world_state

        agent = make_agent_state(
            agent_id=1, profession=Profession.farmer,
            goals=[{"type": "produce", "priority": 1}],
            traits={"warmth": 0.8, "courage": 0.4,
                    "greed": 0.2, "cunning": 0.2, "piety": 0.5},
            food=10.0,
        )
        world = make_world_state(agents=[agent])
        runner = TurnRunner()
        r1 = runner.run_turn(world)
        r2 = runner.run_turn(world)

        assert len(r1.events) == len(r2.events)
        assert len(r1.memories) == len(r2.memories)
        assert len(r1.resolved_actions) == len(r2.resolved_actions)
        assert r1.turn_number == r2.turn_number

    def test_turn_context_not_exposed_in_turn_result(self):
        """TurnContext is an internal pipeline detail; it must not be a field of TurnResult."""
        from app.simulation.types import TurnResult, TurnContext

        for _name, field in TurnResult.model_fields.items():
            annotation = field.annotation
            assert annotation is not TurnContext, (
                "TurnContext (internal pipeline state) must not appear in TurnResult"
            )
