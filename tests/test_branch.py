"""A branch readies only the case whose when-clause matches the signal."""

from mastra_orchestration import Orchestrator


def test_branch_readies_only_the_matching_case():
    graph = {
        "id": "content",
        "chain": [
            {
                "op": "branch",
                "cases": [
                    {"when": {"length": "long"}, "step": {"id": "deep", "agent": "writer", "instruction": "Long"}},
                    {"when": {"length": "short"}, "step": {"id": "quick", "agent": "writer", "instruction": "Short"}},
                ],
            }
        ],
    }
    run = Orchestrator().start(graph, thread="t1", resource="user", signal={"length": "short"})

    assert [step.id for step in run.ready] == ["quick"]


def test_branch_reads_signal_written_by_the_previous_step():
    graph = {
        "id": "content",
        "chain": [
            {"op": "then", "step": {"id": "assess", "agent": "editor", "instruction": "Classify length"}},
            {
                "op": "branch",
                "cases": [
                    {"when": {"length": "long"}, "step": {"id": "deep", "agent": "writer", "instruction": "Long"}},
                    {"when": {"length": "short"}, "step": {"id": "quick", "agent": "writer", "instruction": "Short"}},
                ],
            },
        ],
    }
    orch = Orchestrator()
    run = orch.start(graph, thread="t1", resource="user")
    orch.complete(run, "assess", {"text": "short piece", "signal": {"length": "short"}})

    assert [step.id for step in run.ready] == ["quick"]


def test_unmatched_branch_is_skipped():
    graph = {
        "id": "content",
        "chain": [
            {
                "op": "branch",
                "cases": [
                    {"when": {"length": "long"}, "step": {"id": "deep", "agent": "writer", "instruction": "Long"}},
                ],
            },
            {"op": "then", "step": {"id": "write", "agent": "writer", "instruction": "Draft"}},
        ],
    }
    run = Orchestrator().start(graph, thread="t1", resource="user", signal={"length": "short"})

    assert [step.id for step in run.ready] == ["write"]
