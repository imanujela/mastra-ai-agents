"""A saved run resumes when a worker result is recorded."""

import json

from mastra_orchestration.cli import complete_run, start_run


def test_saved_run_resumes_on_complete(tmp_path):
    graph = {
        "id": "content",
        "chain": [
            {"op": "then", "step": {"id": "research", "agent": "researcher", "instruction": "Find sources"}},
            {"op": "parallel", "steps": [
                {"id": "seo", "agent": "analyst", "instruction": "SEO"},
                {"id": "tone", "agent": "analyst", "instruction": "Tone"},
            ]},
        ],
    }
    started = start_run(tmp_path, graph, thread="t1", resource="user")

    assert started["status"] == "running"
    assert [step["id"] for step in started["ready"]] == ["research"]
    assert started["ready"][0]["memory_thread"] == "t1"

    resumed = complete_run(tmp_path, started["run_id"], "research", {"text": "sources"})

    assert {step["id"] for step in resumed["ready"]} == {"seo", "tone"}
    assert json.loads((tmp_path / "runs" / f"{started['run_id']}.json").read_text(encoding="utf-8"))["status"] == "running"
