"""Durable run storage: the run file is the truth, the index is a cache."""

import json

import pytest

from mastra_ai_agents.store import RunStore
from mastra_ai_agents.types import DONE, RUNNING, Run, Step


def make_run(run_id="run-1", updated_at="2026-10-21T10:00:00+00:00", status=RUNNING, thread="thread-1"):
    return Run(
        id=run_id,
        graph_id="graph-1",
        status=status,
        ready=[
            Step(id="s1", agent="researcher", instruction="look"),
            Step(id="s2", agent="writer", instruction="write"),
        ],
        outputs={"s1": {"text": "found"}},
        signal={"topic": "storage"},
        thread=thread,
        resource="resource-1",
        chain=[{"op": "then", "step": {"id": "s1"}}],
        index=1,
        pending=["s2"],
        iterations={"loop-1": 2},
        attempts={"s1": 1},
        note="halfway",
        created_at="2026-10-21T09:00:00+00:00",
        updated_at=updated_at,
    )


def test_save_then_load_round_trips_by_field_values(tmp_path):
    store = RunStore(tmp_path)
    run = make_run()

    path = store.save(run)

    assert path == tmp_path / "runs" / "run-1.json"
    assert store.load("run-1").to_dict() == run.to_dict()


def test_save_leaves_no_tmp_file_and_index_records_the_run(tmp_path):
    store = RunStore(tmp_path)

    store.save(make_run())

    runs_dir = tmp_path / "runs"
    assert list(runs_dir.glob("*.tmp")) == []
    index = json.loads((runs_dir / "index.json").read_text(encoding="utf-8"))
    assert index["runs"]["run-1"] == {
        "id": "run-1",
        "graph_id": "graph-1",
        "status": RUNNING,
        "thread": "thread-1",
        "resource": "resource-1",
        "ready": 2,
        "created_at": "2026-10-21T09:00:00+00:00",
        "updated_at": "2026-10-21T10:00:00+00:00",
    }


def test_load_missing_raises_file_not_found_with_the_path(tmp_path):
    store = RunStore(tmp_path)

    with pytest.raises(FileNotFoundError) as excinfo:
        store.load("nope")

    assert str(tmp_path / "runs" / "nope.json") in str(excinfo.value)


def test_exists_is_true_only_for_saved_runs(tmp_path):
    store = RunStore(tmp_path)

    assert store.exists("run-1") is False
    store.save(make_run())
    assert store.exists("run-1") is True
    store.delete("run-1")
    assert store.exists("run-1") is False


def test_delete_removes_the_run_file_its_event_log_and_index_entry(tmp_path):
    store = RunStore(tmp_path)
    store.save(make_run())
    events = tmp_path / "runs" / "run-1.events.jsonl"
    events.write_text('{"event": "started"}\n', encoding="utf-8")

    assert store.delete("run-1") is True

    assert not (tmp_path / "runs" / "run-1.json").exists()
    assert not events.exists()
    index = json.loads((tmp_path / "runs" / "index.json").read_text(encoding="utf-8"))
    assert "run-1" not in index["runs"]
    assert store.delete("run-1") is False


def test_save_does_not_mutate_the_run(tmp_path):
    store = RunStore(tmp_path)
    run = make_run()
    before = run.to_dict()

    store.save(run)

    assert run.to_dict() == before
    assert run.status == RUNNING
    assert run.updated_at == "2026-10-21T10:00:00+00:00"
    assert store.load("run-1").status == RUNNING


def test_index_is_rebuilt_from_run_files_when_deleted(tmp_path):
    store = RunStore(tmp_path)
    store.save(make_run("run-1", updated_at="2026-10-21T10:00:00+00:00"))
    store.save(make_run("run-2", updated_at="2026-10-21T11:00:00+00:00"))
    (tmp_path / "runs" / "index.json").unlink()

    entries = store.list()

    assert [entry["id"] for entry in entries] == ["run-2", "run-1"]
    assert json.loads((tmp_path / "runs" / "index.json").read_text(encoding="utf-8"))["runs"]


def test_corrupt_index_is_healed_from_run_files(tmp_path):
    store = RunStore(tmp_path)
    store.save(make_run("run-1"))
    (tmp_path / "runs" / "index.json").write_text("{not json", encoding="utf-8")

    entries = store.list()

    assert [entry["id"] for entry in entries] == ["run-1"]
    assert store.latest()["id"] == "run-1"


def test_list_is_newest_updated_first_filters_status_and_limits(tmp_path):
    store = RunStore(tmp_path)
    store.save(make_run("old", updated_at="2026-10-21T09:00:00+00:00", status=RUNNING))
    store.save(make_run("middle", updated_at="2026-10-21T10:00:00+00:00", status=DONE))
    store.save(make_run("new", updated_at="2026-10-21T11:00:00+00:00", status=DONE))

    assert [entry["id"] for entry in store.list()] == ["new", "middle", "old"]
    assert [entry["id"] for entry in store.list(status=DONE)] == ["new", "middle"]
    assert [entry["id"] for entry in store.list(limit=2)] == ["new", "middle"]
    assert store.list(status="failed") == []


def test_latest_can_be_narrowed_to_one_thread(tmp_path):
    store = RunStore(tmp_path)
    store.save(make_run("other", updated_at="2026-10-21T11:00:00+00:00", thread="thread-1"))
    store.save(make_run("mine", updated_at="2026-10-21T10:00:00+00:00", thread="thread-2"))

    assert store.latest()["id"] == "other"
    assert store.latest(thread="thread-1")["id"] == "other"
    assert store.latest(thread="thread-2")["id"] == "mine"
    assert store.latest(thread="missing") is None


def test_an_untouched_store_lists_nothing_and_deletes_nothing(tmp_path):
    store = RunStore(tmp_path)

    assert store.list() == []
    assert store.latest() is None
    assert store.delete("absent") is False
    assert store.exists("absent") is False


def test_a_stale_tmp_file_never_becomes_the_run(tmp_path):
    store = RunStore(tmp_path)
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir(parents=True)
    (runs_dir / "run-1.json.tmp").write_text("{torn", encoding="utf-8")

    store.save(make_run())

    assert store.load("run-1").id == "run-1"
    assert list(runs_dir.glob("*.tmp")) == []
