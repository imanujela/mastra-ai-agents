"""The blackboard is the run's shared field: workers post, later workers read."""

import json

import pytest

from mastra_ai_agents.blackboard import Blackboard


def test_post_returns_an_entry_with_identity_and_time(tmp_path):
    board = Blackboard(tmp_path)
    entry = board.post("r1", "dig#0", "finding", "Three sources", "A, B, C", tags=["sources"])

    assert entry["id"] == "e1"
    assert entry["run_id"] == "r1"
    assert entry["step_id"] == "dig#0"
    assert entry["kind"] == "finding"
    assert entry["title"] == "Three sources"
    assert entry["body"] == "A, B, C"
    assert entry["tags"] == ["sources"]
    assert entry["ts"].endswith("+00:00")


def test_entries_are_chronological_and_filterable(tmp_path):
    board = Blackboard(tmp_path)
    board.post("r1", "a", "finding", "first", tags=["x"])
    board.post("r1", "b", "risk", "second", tags=["y"])
    board.post("r1", "c", "finding", "third", tags=["x"])

    assert [e["title"] for e in board.entries("r1")] == ["first", "second", "third"]
    assert [e["title"] for e in board.entries("r1", tag="x")] == ["first", "third"]
    assert [e["title"] for e in board.entries("r1", kind="risk")] == ["second"]
    assert board.entries("unknown") == []


def test_digest_is_bounded_and_names_the_poster(tmp_path):
    board = Blackboard(tmp_path)
    for index in range(30):
        board.post("r1", f"step-{index}", "finding", f"title-{index}", body="x" * 400)

    digest = board.digest("r1", limit=5)

    assert "title-29" in digest
    assert "step-29" in digest
    assert "title-24" not in digest
    assert len(digest) < 1200


def test_prune_keeps_the_newest_entries(tmp_path):
    board = Blackboard(tmp_path)
    for index in range(10):
        board.post("r1", "s", "note", f"t{index}")

    removed = board.prune("r1", keep=4)

    assert removed == 6
    assert [e["title"] for e in board.entries("r1")] == ["t6", "t7", "t8", "t9"]


def test_entries_survive_a_new_instance(tmp_path):
    Blackboard(tmp_path).post("r1", "a", "finding", "kept", body="body")
    assert [e["title"] for e in Blackboard(tmp_path).entries("r1")] == ["kept"]


def test_writes_leave_no_tmp_file_and_stay_valid_json(tmp_path):
    board = Blackboard(tmp_path)
    board.post("r1", "a", "finding", "one")

    files = sorted(path.name for path in (tmp_path / "blackboard").iterdir())
    assert files == ["r1.json"]
    json.loads((tmp_path / "blackboard" / "r1.json").read_text(encoding="utf-8"))


def test_corrupt_board_is_reported_not_silently_truncated(tmp_path):
    path = tmp_path / "blackboard"
    path.mkdir()
    (path / "r1.json").write_text("{not json", encoding="utf-8")

    with pytest.raises(ValueError):
        Blackboard(tmp_path).entries("r1")


def test_post_rejects_an_empty_title(tmp_path):
    with pytest.raises(ValueError):
        Blackboard(tmp_path).post("r1", "a", "finding", "")
