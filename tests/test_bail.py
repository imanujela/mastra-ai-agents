"""A worker bail stops the supervisor before later steps run."""

from mastra_orchestration import Orchestrator


def test_bail_stops_the_supervisor_before_later_steps():
    graph = {
        "id": "content",
        "chain": [
            {"op": "then", "step": {"id": "research", "agent": "researcher", "instruction": "Find sources"}},
            {"op": "then", "step": {"id": "write", "agent": "writer", "instruction": "Draft"}},
        ],
    }
    orch = Orchestrator()
    run = orch.start(graph, thread="t1", resource="user")

    orch.complete(run, "research", {"text": "stop", "bail": True})

    assert run.status == "bailed"
    assert run.ready == []
