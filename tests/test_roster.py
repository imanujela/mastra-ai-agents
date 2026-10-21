"""A worker without its own memory receives the parent thread."""

from mastra_orchestration import Orchestrator


def test_worker_without_own_memory_receives_the_parent_thread():
    graph = {
        "id": "content",
        "chain": [
            {"op": "then", "step": {"id": "research", "agent": "researcher", "instruction": "Find sources"}},
            {"op": "then", "step": {"id": "write", "agent": "writer", "instruction": "Draft"}},
        ],
    }
    orch = Orchestrator(roster={"researcher": {"own_memory": False}, "writer": {"own_memory": True}})
    run = orch.start(graph, thread="t1", resource="user")

    assert run.ready[0].memory_thread == "t1"
    assert run.ready[0].resource == "user"

    orch.complete(run, "research", {"text": "sources"})
    assert run.ready[0].id == "write"
    assert run.ready[0].memory_thread is None
