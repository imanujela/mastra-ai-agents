"""Working memory and observations survive a recall on the same thread."""

from mastra_orchestration import Memory


def test_recall_returns_merged_working_memory_and_observations(tmp_path):
    memory = Memory(tmp_path)
    memory.remember(thread="t1", resource="user", working_memory={"city": "Oslo"}, observation="prefers short drafts")
    memory.remember(thread="t1", resource="user", working_memory={"tone": "plain"})

    recalled = memory.recall(thread="t1", resource="user")

    assert recalled.working_memory == {"city": "Oslo", "tone": "plain"}
    assert recalled.observations == ["prefers short drafts"]
