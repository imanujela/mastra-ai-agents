"""Expanding operators: foreach item batches and loop iterations."""

import pytest

from mastra_ai_agents.engine import Orchestrator
from mastra_ai_agents.types import Run


def _step(step_id, instruction="Work", **extra):
    return {"id": step_id, "agent": "worker", "instruction": instruction, **extra}


def _then(step_id):
    return {"op": "then", "step": _step(step_id)}


def _foreach(over, steps, **extra):
    return {"op": "foreach", "over": over, "steps": steps, **extra}


def _loop(steps, until, max_iterations):
    return {
        "op": "loop",
        "steps": steps,
        "until": until,
        "max_iterations": max_iterations,
    }


def test_foreach_expands_one_batch_per_item_in_order():
    graph = {
        "id": "blog",
        "chain": [
            _foreach(
                "topics",
                [_step("draft", "Draft {{item}}"), _step("edit", "Edit")],
            ),
            _then("publish"),
        ],
    }
    run = Orchestrator().start(
        graph, thread="t1", resource="user", signal={"topics": ["alpha", "beta"]}
    )

    assert run.ready_ids() == ["draft#0", "edit#0", "draft#1", "edit#1"]
    assert run.pending == ["draft#0", "edit#0", "draft#1", "edit#1"]
    assert [step.meta["item"] for step in run.ready] == ["alpha", "alpha", "beta", "beta"]
    assert [step.meta["index"] for step in run.ready] == [0, 0, 1, 1]
    assert [step.instruction for step in run.ready] == [
        "Draft alpha",
        "Edit",
        "Draft beta",
        "Edit",
    ]
    assert Run.from_dict(run.to_dict()) == run


def test_foreach_waits_for_every_copy_before_advancing():
    graph = {
        "id": "blog",
        "chain": [
            _foreach("topics", [_step("draft", "Draft {{item}}")]),
            _then("publish"),
        ],
    }
    orch = Orchestrator()
    run = orch.start(graph, thread="t1", resource="user", signal={"topics": ["alpha", "beta"]})

    orch.complete(run, "draft#0", {"text": "alpha"})
    assert run.ready_ids() == ["draft#1"]
    assert run.status == "running"

    orch.complete(run, "draft#1", {"text": "beta"})
    assert run.ready_ids() == ["publish"]


def test_foreach_templates_every_occurrence_of_the_item():
    graph = {
        "id": "blog",
        "chain": [_foreach("topics", [_step("draft", "Draft {{item}} about {{item}}")])],
    }
    run = Orchestrator().start(graph, thread="t1", resource="user", signal={"topics": ["bread"]})

    assert run.ready[0].instruction == "Draft bread about bread"


def test_foreach_records_max_parallel_and_keeps_step_meta():
    graph = {
        "id": "blog",
        "chain": [
            _foreach(
                "topics",
                [_step("draft", "Draft {{item}}", meta={"role": "draft"})],
                max_parallel=2,
            ),
            _then("publish"),
        ],
    }
    run = Orchestrator().start(graph, thread="t1", resource="user", signal={"topics": ["alpha"]})

    assert run.ready[0].meta == {"role": "draft", "item": "alpha", "index": 0, "max_parallel": 2}

    plain = Orchestrator().start(
        {"id": "blog", "chain": [_foreach("topics", [_step("draft")])]},
        thread="t1",
        resource="user",
        signal={"topics": ["alpha"]},
    )
    assert "max_parallel" not in plain.ready[0].meta


def test_foreach_with_an_empty_list_is_skipped():
    graph = {
        "id": "blog",
        "chain": [_foreach("topics", [_step("draft")]), _then("publish")],
    }
    run = Orchestrator().start(graph, thread="t1", resource="user", signal={"topics": []})

    assert run.ready_ids() == ["publish"]
    assert run.index == 1


def test_foreach_requires_a_list_in_the_signal():
    graph = {
        "id": "blog",
        "chain": [_foreach("topics", [_step("draft")]), _then("publish")],
    }

    with pytest.raises(ValueError, match="topics"):
        Orchestrator().start(graph, thread="t1", resource="user", signal={"topics": "alpha"})
    with pytest.raises(ValueError, match="topics"):
        Orchestrator().start(graph, thread="t1", resource="user")


def test_foreach_applies_roster_memory_rules_to_each_copy():
    graph = {
        "id": "blog",
        "chain": [
            _foreach(
                "topics",
                [
                    _step("draft", "Draft", agent="writer"),
                    _step("edit", "Edit", agent="editor"),
                ],
            )
        ],
    }
    roster = {"writer": {"own_memory": True}, "editor": {"own_memory": False}}
    run = Orchestrator(roster=roster).start(
        graph, thread="t1", resource="user", signal={"topics": ["alpha"]}
    )

    by_id = {step.id: step for step in run.ready}
    assert by_id["draft#0"].memory_thread is None
    assert by_id["draft#0"].resource is None
    assert by_id["edit#0"].memory_thread == "t1"
    assert by_id["edit#0"].resource == "user"


def test_loop_repeats_then_stops_when_until_matches():
    graph = {
        "id": "review",
        "chain": [
            _loop([_step("review", "Review")], until={"approved": True}, max_iterations=5),
            _then("publish"),
        ],
    }
    orch = Orchestrator()
    run = orch.start(graph, thread="t1", resource="user")

    assert run.ready_ids() == ["review#r1"]
    assert run.iterations == {"0": 1}

    orch.complete(run, "review#r1", {"text": "needs work", "signal": {"approved": False}})

    assert run.ready_ids() == ["review#r2"]
    assert run.iterations == {"0": 2}
    assert run.index == 0
    assert Run.from_dict(run.to_dict()) == run

    orch.complete(run, "review#r2", {"text": "ship it", "signal": {"approved": True}})

    assert run.ready_ids() == ["publish"]
    assert run.index == 1
    assert run.iterations == {"0": 2}


def test_loop_stops_at_the_iteration_cap():
    graph = {
        "id": "review",
        "chain": [
            _loop([_step("review", "Review")], until={"approved": True}, max_iterations=2),
            _then("publish"),
        ],
    }
    orch = Orchestrator()
    run = orch.start(graph, thread="t1", resource="user")

    orch.complete(run, "review#r1", {"text": "no"})
    assert run.ready_ids() == ["review#r2"]

    orch.complete(run, "review#r2", {"text": "still no"})
    assert run.ready_ids() == ["publish"]
    assert run.iterations == {"0": 2}


def test_loop_waits_for_every_step_in_the_block():
    graph = {
        "id": "build",
        "chain": [
            _loop(
                [_step("plan", "Plan"), _step("build", "Build")],
                until={"built": True},
                max_iterations=3,
            )
        ],
    }
    orch = Orchestrator()
    run = orch.start(graph, thread="t1", resource="user")

    assert run.ready_ids() == ["plan#r1", "build#r1"]

    orch.complete(run, "plan#r1", {"text": "planned"})
    assert run.ready_ids() == ["build#r1"]
    assert run.iterations == {"0": 1}

    orch.complete(run, "build#r1", {"text": "built"})
    assert run.ready_ids() == ["plan#r2", "build#r2"]
    assert run.iterations == {"0": 2}


def test_retry_restores_a_foreach_copy_from_the_graph():
    graph = {
        "id": "blog",
        "chain": [_foreach("topics", [_step("draft", "Draft {{item}}")])],
    }
    orch = Orchestrator()
    run = orch.start(graph, thread="t1", resource="user", signal={"topics": ["alpha", "beta"]})
    orch.complete(run, "draft#0", {"text": "bad"})

    orch.retry(run, "draft#0")

    assert set(run.ready_ids()) == {"draft#0", "draft#1"}
    restored = next(step for step in run.ready if step.id == "draft#0")
    assert restored.meta["item"] == "alpha"
    assert restored.instruction == "Draft alpha"


def test_retry_restores_a_loop_iteration_copy_from_the_graph():
    graph = {
        "id": "review",
        "chain": [
            _loop([_step("review", "Review")], until={"approved": True}, max_iterations=3)
        ],
    }
    orch = Orchestrator()
    run = orch.start(graph, thread="t1", resource="user")
    orch.complete(run, "review#r1", {"text": "no"})
    assert run.ready_ids() == ["review#r2"]

    orch.retry(run, "review#r1")

    assert set(run.ready_ids()) == {"review#r1", "review#r2"}
