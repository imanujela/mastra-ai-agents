"""A parallel node readies every step at once and waits for all of them."""

from mastra_orchestration import Orchestrator


def test_parallel_readies_every_step_and_waits():
    graph = {
        "id": "analysis",
        "chain": [
            {
                "op": "parallel",
                "steps": [
                    {"id": "seo", "agent": "analyst", "instruction": "SEO"},
                    {"id": "tone", "agent": "analyst", "instruction": "Tone"},
                ],
            },
            {"op": "then", "step": {"id": "write", "agent": "writer", "instruction": "Draft"}},
        ],
    }
    orch = Orchestrator()
    run = orch.start(graph, thread="t1", resource="user")

    assert {step.id for step in run.ready} == {"seo", "tone"}

    orch.complete(run, "seo", {"text": "seo ok"})
    assert [step.id for step in run.ready] == ["tone"]

    orch.complete(run, "tone", {"text": "tone ok"})
    assert [step.id for step in run.ready] == ["write"]
