"""The swarm layer: template choice, planning, waves, consensus, learning."""

import pytest

from mastra_ai_agents.graph import step_ids
from mastra_ai_agents.policy import Policy
from mastra_ai_agents.swarm import Swarm, build_graph, choose_template, template_of, templates
from mastra_ai_agents.validate import validate_graph


def test_keywords_pick_the_template():
    assert choose_template("research the market landscape") == "research-sweep"
    assert choose_template("build a feature for exports") == "build-feature"
    assert choose_template("audit the security of this module") == "review-sweep"
    assert choose_template("compare the two options and decide") == "debate"


def test_a_goal_with_no_keyword_falls_back_to_the_default():
    assert choose_template("make the thing nicer") == "research-sweep"


def test_an_explicit_template_wins_and_an_unknown_one_is_named():
    assert choose_template("build a feature", preferred="debate") == "debate"
    with pytest.raises(ValueError):
        choose_template("anything", preferred="telepathy")


def test_the_policy_breaks_a_tie_between_matching_templates(tmp_path):
    policy = Policy(tmp_path / "policy.json")
    policy.observe("research-sweep", "failed")
    policy.observe("research-sweep", "failed")

    assert choose_template("review and research the codebase", policy=policy) == "review-sweep"


def test_every_template_builds_a_valid_graph_with_unique_ids():
    for name in templates():
        graph = build_graph("ship the export feature", name)
        assert validate_graph(graph) == [], name
        ids = step_ids(graph["chain"])
        assert len(ids) == len(set(ids)), name


def test_the_graph_id_names_the_template_and_the_goal():
    graph = build_graph("Ship the Export Feature!", "build-feature")

    assert graph["id"].startswith("build-feature:")
    assert template_of(graph["id"]) == "build-feature"
    assert " " not in graph["id"]


def test_open_persists_the_run_and_its_roster(tmp_path, monkeypatch):
    swarm = Swarm(tmp_path, roster={"scout": {"own_memory": True}})

    run = swarm.open("research the field", thread="t1", resource="user")

    reloaded = swarm.store.load(run.id)
    assert reloaded.id == run.id
    assert reloaded.roster == {"scout": {"own_memory": True}}
    assert [event["event"] for event in swarm.events.read(run.id)] == ["swarm.started"]
    assert reloaded.ready


def test_record_publishes_an_artifact_and_persists(tmp_path):
    swarm = Swarm(tmp_path)
    run = swarm.open("answer this", thread="t1", resource="user", template="blank")

    swarm.record(run, "answer", {"text": "the answer"})

    assert run.status == "done"
    assert [entry["kind"] for entry in swarm.board.entries(run.id)] == ["result"]
    assert swarm.store.load(run.id).outputs["answer"]["text"] == "the answer"


def test_a_finished_run_teaches_the_policy(tmp_path):
    swarm = Swarm(tmp_path)
    run = swarm.open("answer this", thread="t1", resource="user", template="blank")

    swarm.record(run, "answer", {"text": "done"})

    assert swarm.policy.snapshot()["templates"]["blank"] == {"attempts": 1, "successes": 1}


def test_consensus_keeps_the_dissent(tmp_path):
    swarm = Swarm(tmp_path)
    run = swarm.open("compare options and decide", thread="t1", resource="user", template="debate")
    assert {step.id for step in swarm.batch(run)} == {"case-a", "case-b", "case-c"}

    swarm.record(run, "case-a", {"text": "short"})
    swarm.record(run, "case-b", {"text": "short"})
    swarm.record(run, "case-c", {"text": "long"})
    verdict = swarm.consensus(run, "debate")

    assert verdict["winner"] == "short"
    assert verdict["support"] == 2
    assert verdict["dissent"] == ["long"]
    assert verdict["ids"] == ["case-a", "case-b", "case-c"]


def test_context_carries_instruction_prior_results_and_policy(tmp_path):
    swarm = Swarm(tmp_path)
    run = swarm.open("answer this", thread="t1", resource="user", template="blank")
    step = run.ready[0]

    first = swarm.context_for(run, step)
    assert "Instruction: answer this" in first
    assert "Policy" in first

    swarm.record(run, "answer", {"text": "prior text"})
    second = swarm.context_for(run, step)
    assert "prior text" in second


def test_verdict_counts_the_field(tmp_path):
    swarm = Swarm(tmp_path)
    run = swarm.open("answer this", thread="t1", resource="user", template="blank")
    swarm.record(run, "answer", {"text": "done"})

    verdict = swarm.verdict(run)

    assert verdict["run_id"] == run.id
    assert verdict["template"] == "blank"
    assert verdict["status"] == "done"
    assert verdict["steps_completed"] == 1
    assert verdict["artifacts"] == 1


def test_recap_names_the_status_and_the_template(tmp_path):
    swarm = Swarm(tmp_path)
    run = swarm.open("answer this", thread="t1", resource="user", template="blank")
    swarm.record(run, "answer", {"text": "done"})

    recap = swarm.recap(run)

    assert "blank" in recap
    assert "done" in recap
    assert run.id in recap
