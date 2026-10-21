"""Core transitions: run construction, then chains, branches, serialization."""

import pytest

from mastra_ai_agents.engine import Orchestrator
from mastra_ai_agents.types import DONE, RUNNING, Run


def _step(step_id, agent="worker", instruction="Work", **extra):
    return {"id": step_id, "agent": agent, "instruction": instruction, **extra}


def _then(step_id, agent="worker", instruction="Work", **extra):
    return {"op": "then", "step": _step(step_id, agent, instruction, **extra)}


def test_start_builds_a_running_run_at_the_first_step():
    graph = {"id": "content", "chain": [_then("research"), _then("write")]}

    run = Orchestrator().start(graph, thread="t1", resource="user", signal={"kind": "blog"})

    assert run.graph_id == "content"
    assert run.chain == graph["chain"]
    assert len(run.id) == 12
    assert run.thread == "t1"
    assert run.resource == "user"
    assert run.signal == {"kind": "blog"}
    assert run.status == RUNNING
    assert run.ready_ids() == ["research"]
    assert run.pending == ["research"]
    assert run.created_at and run.created_at == run.updated_at


def test_completing_then_steps_records_outputs_and_finishes():
    graph = {"id": "content", "chain": [_then("research"), _then("write")]}
    orch = Orchestrator()
    run = orch.start(graph, thread="t1", resource="user")

    assert orch.complete(run, "research", {"text": "sources"}) is run

    assert run.ready_ids() == ["write"]
    assert run.pending == ["write"]
    assert run.outputs["research"] == {"text": "sources"}
    assert run.attempts["research"] == 1
    assert run.status == RUNNING

    orch.complete(run, "write", {"text": "draft"})

    assert run.status == DONE
    assert run.ready == []
    assert run.pending == []
    assert run.outputs["write"] == {"text": "draft"}


def test_complete_rejects_unknown_or_not_yet_ready_steps():
    graph = {"id": "content", "chain": [_then("research"), _then("write")]}
    orch = Orchestrator()
    run = orch.start(graph, thread="t1", resource="user")

    with pytest.raises(KeyError):
        orch.complete(run, "ghost", {})
    with pytest.raises(KeyError):
        orch.complete(run, "write", {})


def _branch(cases, default=None):
    node = {"op": "branch", "cases": cases}
    if default is not None:
        node["default"] = default
    return node


def test_branch_readies_every_matching_case_at_once():
    graph = {
        "id": "g",
        "chain": [
            _branch(
                [
                    {"when": {"kind": "post"}, "step": _step("short")},
                    {"when": {"kind": "post", "tone": "dry"}, "step": _step("dry")},
                    {"when": {"kind": "video"}, "step": _step("video")},
                ],
                default=_step("fallback"),
            ),
            _then("publish"),
        ],
    }
    orch = Orchestrator()
    run = orch.start(graph, thread="t1", resource="user", signal={"kind": "post", "tone": "dry"})

    assert run.ready_ids() == ["short", "dry"]
    assert run.pending == ["short", "dry"]

    orch.complete(run, "short", {"text": "short"})
    assert run.ready_ids() == ["dry"]
    assert run.status == RUNNING

    orch.complete(run, "dry", {"text": "dry"})
    assert run.ready_ids() == ["publish"]


def test_branch_default_runs_only_when_no_case_matches():
    graph = {
        "id": "g",
        "chain": [
            _branch([{"when": {"kind": "post"}, "step": _step("post")}], default=_step("fallback")),
            _then("publish"),
        ],
    }
    orch = Orchestrator()
    run = orch.start(graph, thread="t1", resource="user", signal={"kind": "video"})

    assert run.ready_ids() == ["fallback"]

    orch.complete(run, "fallback", {"text": "made a video"})
    assert run.ready_ids() == ["publish"]


def test_unmatched_branch_without_default_is_skipped():
    graph = {
        "id": "g",
        "chain": [
            _branch([{"when": {"kind": "post"}, "step": _step("post")}]),
            _then("publish"),
        ],
    }
    run = Orchestrator().start(graph, thread="t1", resource="user", signal={"kind": "video"})

    assert run.ready_ids() == ["publish"]
    assert run.index == 1


def test_signal_from_a_completed_step_selects_the_branch():
    graph = {
        "id": "g",
        "chain": [
            _then("classify"),
            _branch(
                [{"when": {"length": "long"}, "step": _step("deep")}],
                default=_step("quick"),
            ),
        ],
    }
    orch = Orchestrator()
    run = orch.start(graph, thread="t1", resource="user")

    orch.complete(run, "classify", {"text": "long piece", "signal": {"length": "long"}})

    assert run.ready_ids() == ["deep"]


def test_run_round_trips_after_every_transition():
    graph = {"id": "content", "chain": [_then("research"), _then("write")]}
    orch = Orchestrator()
    run = orch.start(graph, thread="t1", resource="user", signal={"kind": "blog"})

    assert Run.from_dict(run.to_dict()) == run

    orch.complete(run, "research", {"text": "sources", "signal": {"length": "short"}})
    assert Run.from_dict(run.to_dict()) == run

    orch.complete(run, "write", {"text": "draft"})
    assert Run.from_dict(run.to_dict()) == run

