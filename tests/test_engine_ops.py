"""Batch operations: parallel waits, retry restoration, abort."""

import pytest

from mastra_ai_agents.engine import Orchestrator
from mastra_ai_agents.types import ABORTED, DONE, RUNNING, Run


def _step(step_id, agent="worker", instruction="Work", **extra):
    return {"id": step_id, "agent": agent, "instruction": instruction, **extra}


def _then(step_id, **extra):
    return {"op": "then", "step": _step(step_id, **extra)}


def _parallel(*step_ids):
    return {"op": "parallel", "steps": [_step(step_id) for step_id in step_ids]}


def test_parallel_readies_every_step_and_waits_for_all():
    graph = {"id": "analysis", "chain": [_parallel("seo", "tone"), _then("write")]}
    orch = Orchestrator()
    run = orch.start(graph, thread="t1", resource="user")

    assert set(run.ready_ids()) == {"seo", "tone"}
    assert set(run.pending) == {"seo", "tone"}
    assert run.status == RUNNING

    orch.complete(run, "seo", {"text": "seo ok"})

    assert run.ready_ids() == ["tone"]
    assert run.pending == ["tone"]
    assert run.status == RUNNING

    orch.complete(run, "tone", {"text": "tone ok"})

    assert run.ready_ids() == ["write"]


def test_parallel_completion_order_does_not_matter():
    graph = {"id": "analysis", "chain": [_parallel("seo", "tone"), _then("write")]}
    orch = Orchestrator()
    run = orch.start(graph, thread="t1", resource="user")

    orch.complete(run, "tone", {"text": "tone ok"})
    assert run.ready_ids() == ["seo"]

    orch.complete(run, "seo", {"text": "seo ok"})
    assert run.ready_ids() == ["write"]


def test_retry_restores_a_completed_step():
    graph = {"id": "analysis", "chain": [_parallel("seo", "tone")]}
    orch = Orchestrator()
    run = orch.start(graph, thread="t1", resource="user")
    orch.complete(run, "seo", {"text": "first pass"})

    assert orch.retry(run, "seo") is run

    assert run.status == RUNNING
    assert set(run.ready_ids()) == {"seo", "tone"}
    assert set(run.pending) == {"seo", "tone"}
    assert "seo" not in run.outputs
    assert "seo" not in run.attempts
    retried = next(step for step in run.ready if step.id == "seo")
    assert retried.memory_thread == "t1"
    assert Run.from_dict(run.to_dict()) == run

    orch.complete(run, "seo", {"text": "second pass"})
    assert run.outputs["seo"] == {"text": "second pass"}
    assert run.attempts["seo"] == 1


def test_retry_rejects_unknown_ids_and_terminal_runs():
    graph = {"id": "analysis", "chain": [_parallel("seo", "tone")]}
    orch = Orchestrator()
    run = orch.start(graph, thread="t1", resource="user")

    with pytest.raises(KeyError):
        orch.retry(run, "ghost")

    orch.complete(run, "seo", {})
    orch.complete(run, "tone", {})
    assert run.status == DONE

    with pytest.raises(ValueError):
        orch.retry(run, "seo")


def test_abort_clears_work_and_records_the_reason():
    graph = {"id": "content", "chain": [_parallel("seo", "tone"), _then("write")]}
    orch = Orchestrator()
    run = orch.start(graph, thread="t1", resource="user")
    orch.complete(run, "seo", {"text": "seo ok"})

    assert orch.abort(run, "operator stop") is run

    assert run.status == ABORTED
    assert run.ready == []
    assert run.pending == []
    assert run.note == "operator stop"
    assert run.outputs == {"seo": {"text": "seo ok"}}
    assert Run.from_dict(run.to_dict()) == run
