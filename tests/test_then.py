"""A then-chain exposes only the first step until it completes."""

from mastra_orchestration import Orchestrator


def test_then_chain_readies_the_first_step_only():
    graph = {
        "id": "content",
        "chain": [
            {"op": "then", "step": {"id": "research", "agent": "researcher", "instruction": "Find sources"}},
            {"op": "then", "step": {"id": "write", "agent": "writer", "instruction": "Draft"}},
        ],
    }
    run = Orchestrator().start(graph, thread="t1", resource="user")

    assert [step.id for step in run.ready] == ["research"]
    assert run.status == "running"


def test_completing_a_then_step_readies_the_next():
    graph = {
        "id": "content",
        "chain": [
            {"op": "then", "step": {"id": "research", "agent": "researcher", "instruction": "Find sources"}},
            {"op": "then", "step": {"id": "write", "agent": "writer", "instruction": "Draft"}},
        ],
    }
    orch = Orchestrator()
    run = orch.start(graph, thread="t1", resource="user")

    orch.complete(run, "research", {"text": "sources"})

    assert [step.id for step in run.ready] == ["write"]
    orch.complete(run, "write", {"text": "draft"})
    assert run.ready == []
    assert run.status == "done"
