"""Thread memory: merged working memory, observations, summary and atomic files."""

import json

from mastra_ai_agents.memory import Memory
from mastra_ai_agents.types import Recall


def test_remember_merges_working_memory_and_appends_a_timestamped_observation(tmp_path):
    memory = Memory(tmp_path)

    first = memory.remember(
        "thread-1",
        "user",
        working_memory={"city": "Oslo"},
        observation="prefers short drafts",
    )

    assert isinstance(first, Recall)
    assert first.working_memory == {"city": "Oslo"}
    assert first.texts == ["prefers short drafts"]
    assert first.observations[0]["ts"]

    memory.remember("thread-1", "user", working_memory={"tone": "plain"}, observation="likes bullets")

    recalled = memory.recall("thread-1", "user")
    assert recalled.working_memory == {"city": "Oslo", "tone": "plain"}
    assert recalled.texts == ["prefers short drafts", "likes bullets"]


def test_recall_of_an_unknown_thread_is_empty(tmp_path):
    assert Memory(tmp_path).recall("nobody", "user") == Recall()


def test_observations_must_be_non_empty_strings(tmp_path):
    memory = Memory(tmp_path)

    memory.remember("thread-1", "user", observation="")
    memory.remember("thread-1", "user", observation=None)
    memory.remember("thread-1", "user", observation=123)

    assert memory.recall("thread-1", "user").observations == []


def test_remember_leaves_no_tmp_file_behind(tmp_path):
    memory = Memory(tmp_path)

    memory.remember("thread-1", "user", observation="note")

    assert list(tmp_path.glob("*.tmp")) == []
    files = list(tmp_path.glob("*.json"))
    assert [path.name for path in files] == ["user__thread-1.json"]


def test_summary_is_replaced_when_given_and_kept_otherwise(tmp_path):
    memory = Memory(tmp_path)

    memory.remember("thread-1", "user", summary="first pass")
    assert memory.recall("thread-1", "user").summary == "first pass"

    memory.remember("thread-1", "user", summary="second pass")
    assert memory.recall("thread-1", "user").summary == "second pass"

    memory.remember("thread-1", "user", observation="no summary this time")
    assert memory.recall("thread-1", "user").summary == "second pass"


def test_observations_are_capped_at_the_newest_200(tmp_path):
    memory = Memory(tmp_path)
    for number in range(205):
        memory.remember("thread-1", "user", observation=f"note {number}")

    recalled = memory.recall("thread-1", "user")

    assert len(recalled.observations) == 200
    assert recalled.texts[0] == "note 5"
    assert recalled.texts[-1] == "note 204"


def test_legacy_plain_string_observations_are_coerced(tmp_path):
    legacy = {
        "working_memory": {"city": "Oslo"},
        "observations": ["older note", {"ts": "2026-10-21T09:00:00+00:00", "text": "newer note"}],
    }
    (tmp_path / "user__thread-1.json").write_text(json.dumps(legacy), encoding="utf-8")

    recalled = Memory(tmp_path).recall("thread-1", "user")

    assert recalled.working_memory == {"city": "Oslo"}
    assert recalled.observations == [
        {"ts": "", "text": "older note"},
        {"ts": "2026-10-21T09:00:00+00:00", "text": "newer note"},
    ]


def test_forget_removes_only_that_thread(tmp_path):
    memory = Memory(tmp_path)
    memory.remember("thread-1", "user", observation="one")
    memory.remember("thread-2", "user", observation="two")

    assert memory.forget("thread-1", "user") is True
    assert memory.forget("thread-1", "user") is False
    assert memory.recall("thread-1", "user") == Recall()
    assert memory.recall("thread-2", "user").texts == ["two"]


def test_threads_counts_notes_newest_first_and_filters_by_resource(tmp_path):
    memory = Memory(tmp_path)
    memory.remember("thread-1", "user", observation="one")
    memory.remember("thread-1", "user", observation="two")
    memory.remember("thread-2", "project", observation="three")
    _stamp(tmp_path / "user__thread-1.json", "2026-10-21T09:00:00+00:00")
    _stamp(tmp_path / "project__thread-2.json", "2026-10-21T11:00:00+00:00")

    rows = memory.threads()

    assert rows == [
        {
            "thread": "thread-2",
            "resource": "project",
            "observations": 1,
            "updated_at": "2026-10-21T11:00:00+00:00",
        },
        {
            "thread": "thread-1",
            "resource": "user",
            "observations": 2,
            "updated_at": "2026-10-21T09:00:00+00:00",
        },
    ]
    assert memory.threads(resource="user") == [rows[1]]


def test_threads_skips_corrupt_files(tmp_path):
    memory = Memory(tmp_path)
    memory.remember("thread-1", "user", observation="kept")
    (tmp_path / "user__broken.json").write_text("{not json", encoding="utf-8")
    (tmp_path / "user__partial.json.tmp").write_text("{not json", encoding="utf-8")

    assert [row["thread"] for row in memory.threads()] == ["thread-1"]


def test_slashes_are_flattened_in_the_filename_but_recall_uses_originals(tmp_path):
    memory = Memory(tmp_path)

    memory.remember("a/b", "org\\repo", observation="note")

    assert (tmp_path / "org_repo__a_b.json").is_file()
    assert memory.recall("a/b", "org\\repo").texts == ["note"]

    rows = memory.threads(resource="org\\repo")
    assert len(rows) == 1
    assert rows[0]["thread"] == "a_b"
    assert rows[0]["resource"] == "org_repo"
    assert rows[0]["observations"] == 1
    assert rows[0]["updated_at"]


def _stamp(path, stamp):
    data = json.loads(path.read_text(encoding="utf-8"))
    data["updated_at"] = stamp
    path.write_text(json.dumps(data), encoding="utf-8")
