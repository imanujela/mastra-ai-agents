"""Failure paths: retries, exhaustion, bail, abort, and their id contracts."""

import pytest

from mastra_ai_agents.engine import Orchestrator
from mastra_ai_agents.types import ABORTED, BAILED, DONE, FAILED, RUNNING, Run


def _step(step_id, retries=0):
    return {
        "id": step_id,
        "agent": "worker",
        "instruction": "Work",
        "retries": retries,
    }


def _then(step_id, retries=0):
    return {"op": "then", "step": _step(step_id, retries)}


def test_error_is_retried_until_the_step_succeeds():
    graph = {"id": "flaky", "chain": [_then("fetch", retries=2)]}
    orch = Orchestrator()
    run = orch.start(graph, thread="t1", resource="user")

    orch.complete(run, "fetch", {"error": "timeout"})

    assert run.status == RUNNING
    assert run.ready_ids() == ["fetch"]
    assert run.pending == ["fetch"]
    assert run.attempts["fetch"] == 1
    assert Run.from_dict(run.to_dict()) == run

    orch.complete(run, "fetch", {"error": "still down"})
    assert run.ready_ids() == ["fetch"]
    assert run.attempts["fetch"] == 2

    orch.complete(run, "fetch", {"text": "ok"})

    assert run.status == DONE
    assert run.attempts["fetch"] == 3
    assert run.outputs["fetch"] == {"text": "ok"}


def test_error_after_the_retry_budget_fails_the_run():
    graph = {"id": "flaky", "chain": [_then("fetch", retries=1), _then("write")]}
    orch = Orchestrator()
    run = orch.start(graph, thread="t1", resource="user")

    orch.complete(run, "fetch", {"error": "first"})
    assert run.status == RUNNING

    orch.complete(run, "fetch", {"error": "gave up"})

    assert run.status == FAILED
    assert run.note == "gave up"
    assert run.ready == []
    assert run.pending == []
    assert run.attempts["fetch"] == 2
    assert "write" not in run.outputs


def test_error_without_a_retry_budget_fails_immediately():
    graph = {"id": "flaky", "chain": [_then("fetch")]}
    orch = Orchestrator()
    run = orch.start(graph, thread="t1", resource="user")

    orch.complete(run, "fetch", {"error": "boom"})

    assert run.status == FAILED
    assert run.note == "boom"
    assert run.attempts["fetch"] == 1


def test_error_on_a_parallel_step_keeps_its_siblings_in_flight():
    graph = {
        "id": "analysis",
        "chain": [
            {"op": "parallel", "steps": [_step("seo", retries=1), _step("tone")]},
            _then("write"),
        ],
    }
    orch = Orchestrator()
    run = orch.start(graph, thread="t1", resource="user")

    orch.complete(run, "seo", {"error": "rate limited"})

    assert run.status == RUNNING
    assert set(run.ready_ids()) == {"seo", "tone"}
    assert set(run.pending) == {"seo", "tone"}

    orch.complete(run, "tone", {"text": "tone ok"})
    assert run.ready_ids() == ["seo"]

    orch.complete(run, "seo", {"text": "seo ok"})
    assert run.ready_ids() == ["write"]


def test_bail_ends_the_run_before_later_steps():
    graph = {"id": "content", "chain": [_then("research"), _then("write")]}
    orch = Orchestrator()
    run = orch.start(graph, thread="t1", resource="user")

    orch.complete(run, "research", {"text": "stop", "bail": True})

    assert run.status == BAILED
    assert run.ready == []
    assert run.pending == []
    assert run.outputs == {"research": {"text": "stop", "bail": True}}
    assert Run.from_dict(run.to_dict()) == run


def test_bail_takes_precedence_over_an_error_in_the_same_result():
    graph = {"id": "content", "chain": [_then("research"), _then("write")]}
    orch = Orchestrator()
    run = orch.start(graph, thread="t1", resource="user")

    orch.complete(run, "research", {"bail": True, "error": "worker vanished"})

    assert run.status == BAILED
    assert run.note == ""


def test_aborted_run_refuses_further_completion():
    graph = {"id": "content", "chain": [_then("research"), _then("write")]}
    orch = Orchestrator()
    run = orch.start(graph, thread="t1", resource="user")

    orch.abort(run, "operator stop")

    assert run.status == ABORTED
    with pytest.raises(KeyError):
        orch.complete(run, "research", {"text": "late"})
    with pytest.raises(ValueError):
        orch.retry(run, "write")


def test_failed_run_is_terminal_and_round_trips():
    graph = {"id": "flaky", "chain": [_then("fetch")]}
    orch = Orchestrator()
    run = orch.start(graph, thread="t1", resource="user")
    orch.complete(run, "fetch", {"error": "boom"})

    assert run.is_terminal
    assert Run.from_dict(run.to_dict()) == run
    with pytest.raises(KeyError):
        orch.complete(run, "fetch", {"text": "late"})
