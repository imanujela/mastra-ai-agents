"""The policy is what one run teaches the next: a smoothed success rate per template."""

import json

import pytest

from mastra_ai_agents.policy import Policy


def test_observe_returns_the_smoothed_rate_for_that_template(tmp_path):
    policy = Policy(tmp_path / "policy.json")

    after_success = policy.observe("research-sweep", "done")

    assert after_success == {"attempts": 1, "successes": 1, "rate": 0.6667}


def test_failures_lower_the_rate_and_rank_reflects_it(tmp_path):
    policy = Policy(tmp_path / "policy.json")
    policy.observe("research-sweep", "failed")
    policy.observe("research-sweep", "failed")
    policy.observe("build-feature", "done")

    assert policy.rank(["research-sweep", "build-feature"]) == ["build-feature", "research-sweep"]


def test_unseen_templates_rank_behind_seen_ones_and_keep_input_order(tmp_path):
    policy = Policy(tmp_path / "policy.json")
    policy.observe("known", "done")

    assert policy.rank(["zebra", "known", "apple"]) == ["known", "zebra", "apple"]


def test_policy_survives_a_new_instance(tmp_path):
    path = tmp_path / "policy.json"
    Policy(path).observe("known", "done")
    Policy(path).observe("known", "done")

    snapshot = Policy(path).snapshot()

    assert snapshot["templates"]["known"] == {"attempts": 2, "successes": 2}


def test_corrupt_policy_resets_instead_of_blocking_a_run(tmp_path):
    path = tmp_path / "policy.json"
    path.write_text("{broken", encoding="utf-8")

    policy = Policy(path)
    policy.observe("known", "done")

    assert policy.snapshot()["templates"]["known"]["attempts"] == 1


def test_snapshot_is_json_serialisable_and_has_no_tmp_sibling(tmp_path):
    path = tmp_path / "policy.json"
    Policy(path).observe("known", "bailed")

    json.loads(path.read_text(encoding="utf-8"))
    assert sorted(p.name for p in tmp_path.iterdir()) == ["policy.json"]


def test_to_context_names_the_best_templates(tmp_path):
    policy = Policy(tmp_path / "policy.json")
    policy.observe("research-sweep", "done")
    policy.observe("build-feature", "failed")

    context = policy.to_context()

    assert "research-sweep" in context
    assert "build-feature" in context
    assert len(context.splitlines()) <= 5


def test_observe_rejects_a_non_terminal_outcome(tmp_path):
    policy = Policy(tmp_path / "policy.json")

    with pytest.raises(ValueError):
        policy.observe("known", "running")
