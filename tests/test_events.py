"""The event log is append-only JSONL: replay what happened, tolerate a torn tail."""

import json

from mastra_ai_agents.events import EventLog


def test_append_writes_one_json_line_and_returns_the_record(tmp_path):
    log = EventLog(tmp_path / "runs")

    record = log.append("run-1", "started", step="s1", agent="researcher")

    lines = (tmp_path / "runs" / "run-1.events.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0]) == record
    assert record["ts"]
    assert record["run_id"] == "run-1"
    assert record["event"] == "started"
    assert record["step"] == "s1"
    assert record["agent"] == "researcher"


def test_append_accumulates_in_order_without_rewriting(tmp_path):
    log = EventLog(tmp_path / "runs")
    log.append("run-1", "started")
    log.append("run-1", "completed", step="s1")
    log.append("run-2", "started")

    events = log.read("run-1")

    assert [event["event"] for event in events] == ["started", "completed"]
    assert events[1]["step"] == "s1"
    assert [event["event"] for event in log.read("run-2")] == ["started"]


def test_read_returns_empty_for_an_unknown_run(tmp_path):
    assert EventLog(tmp_path / "runs").read("never-ran") == []


def test_append_creates_the_runs_directory(tmp_path):
    runs_dir = tmp_path / "nested" / "runs"

    EventLog(runs_dir).append("run-1", "started")

    assert (runs_dir / "run-1.events.jsonl").is_file()


def test_read_skips_unparseable_and_non_object_lines(tmp_path):
    log = EventLog(tmp_path / "runs")
    log.append("run-1", "started")
    path = tmp_path / "runs" / "run-1.events.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write('{"event": "torn"\n')
        handle.write("\n")
        handle.write("[1, 2, 3]\n")
    log.append("run-1", "completed")

    events = log.read("run-1")

    assert [event["event"] for event in events] == ["started", "completed"]


def test_tail_returns_the_last_n_events(tmp_path):
    log = EventLog(tmp_path / "runs")
    for number in range(1, 6):
        log.append("run-1", f"event-{number}")

    assert [event["event"] for event in log.tail("run-1", 2)] == ["event-4", "event-5"]
    assert len(log.tail("run-1")) == 5
    assert log.tail("run-1", 0) == []
    assert log.tail("never-ran") == []
