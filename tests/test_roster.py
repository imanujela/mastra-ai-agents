"""Roster parsing and the memory identity each step receives."""

import pytest

from mastra_ai_agents.roster import parse_roster, resolve_step
from mastra_ai_agents.types import Run, Step


def _run(thread="t1", resource="user"):
    return Run(id="r1", thread=thread, resource=resource)


def _raw(agent="writer", **extra):
    return {
        "id": "s1",
        "agent": agent,
        "instruction": "Draft",
        "retries": 2,
        "timeout_s": 30,
        "meta": {"role": "draft"},
        **extra,
    }


def test_parse_roster_accepts_a_missing_roster():
    assert parse_roster(None) == {}
    assert parse_roster({}) == {}


def test_parse_roster_returns_a_copy_and_keeps_extra_fields():
    raw = {"writer": {"own_memory": True, "model": "local"}}

    parsed = parse_roster(raw)
    parsed["writer"]["model"] = "changed"

    assert raw["writer"]["model"] == "local"
    assert raw["writer"]["own_memory"] is True


def test_parse_roster_names_the_agent_with_a_bad_entry():
    with pytest.raises(ValueError, match="researcher"):
        parse_roster({"researcher": "own"})


def test_parse_roster_names_the_agent_with_a_non_bool_own_memory():
    with pytest.raises(ValueError, match="writer"):
        parse_roster({"writer": {"own_memory": "yes"}})


def test_resolve_step_inherits_the_run_identity():
    step = resolve_step(_raw(), _run(), {})

    assert isinstance(step, Step)
    assert step.memory_thread == "t1"
    assert step.resource == "user"


def test_resolve_step_own_memory_agent_keeps_its_own_identity():
    step = resolve_step(_raw(), _run(), {"writer": {"own_memory": True}})

    assert step.memory_thread is None
    assert step.resource is None


def test_resolve_step_unknown_agent_inherits_the_run_identity():
    step = resolve_step(_raw(agent="stranger"), _run(), {"writer": {"own_memory": True}})

    assert step.memory_thread == "t1"
    assert step.resource == "user"


def test_resolve_step_carries_execution_budget_and_copies_meta():
    raw = _raw()

    step = resolve_step(raw, _run(), {})
    step.meta["role"] = "changed"

    assert step.retries == 2
    assert step.timeout_s == 30
    assert raw["meta"]["role"] == "draft"


def test_resolve_step_defaults_budget_fields():
    step = resolve_step({"id": "s2", "agent": "writer", "instruction": "Go"}, _run(), {})

    assert step.retries == 0
    assert step.timeout_s is None
    assert step.meta == {}
