"""The CLI is the contract: one JSON object per call, exit codes that mean something."""

import json

import pytest

from mastra_ai_agents.cli import main


@pytest.fixture
def cli(tmp_path, capsys):
    def call(*argv):
        code = main(["--root", str(tmp_path / "store"), *argv])
        captured = capsys.readouterr().out
        return code, json.loads(captured)

    return call


@pytest.fixture
def graph_file(tmp_path):
    graph = {
        "id": "content",
        "chain": [
            {"op": "then", "step": {"id": "research", "agent": "researcher", "instruction": "Find sources."}},
            {"op": "parallel", "steps": [
                {"id": "seo", "agent": "analyst", "instruction": "SEO."},
                {"id": "tone", "agent": "analyst", "instruction": "Tone."},
            ]},
            {"op": "branch", "cases": [
                {"when": {"length": "short"}, "step": {"id": "quick", "agent": "writer", "instruction": "Short."}},
            ]},
        ],
    }
    path = tmp_path / "content.json"
    path.write_text(json.dumps(graph), encoding="utf-8")
    return str(path)


def test_a_run_walks_to_done_through_every_op(cli, graph_file):
    code, started = cli("start", "--graph", graph_file, "--thread", "t1", "--resource", "user")
    assert code == 0
    assert started["status"] == "running"
    assert [step["id"] for step in started["ready"]] == ["research"]

    code, after = cli(
        "complete", "--run", started["id"], "--step", "research",
        "--result", json.dumps({"text": "sources", "signal": {"length": "short"}}),
    )
    assert code == 0
    assert {step["id"] for step in after["ready"]} == {"seo", "tone"}

    cli("complete", "--run", started["id"], "--step", "seo", "--result", '{"text":"ok"}')
    _, after = cli("complete", "--run", started["id"], "--step", "tone", "--result", '{"text":"ok"}')
    assert [step["id"] for step in after["ready"]] == ["quick"]

    _, done = cli("complete", "--run", started["id"], "--step", "quick", "--result", '{"text":"draft"}')
    assert done["status"] == "done"
    assert done["ready"] == []


def test_status_reports_a_saved_run(cli, graph_file):
    _, started = cli("start", "--graph", graph_file, "--thread", "t1", "--resource", "user")

    code, status = cli("status", "--run", started["id"])

    assert code == 0
    assert status["run_id"] == started["id"]
    assert status["ready"] == ["research"]
    assert status["chain_length"] == 3


def test_an_invalid_graph_exits_two_with_problems(cli, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"id": "x", "chain": [{"op": "teleport"}]}), encoding="utf-8")

    code, payload = cli("validate", "--graph", str(bad))

    assert code == 2
    assert payload["valid"] is False
    assert payload["problems"]


def test_a_missing_run_exits_three(cli):
    code, payload = cli("status", "--run", "nope")

    assert code == 3
    assert "not found" in payload["error"]


def test_a_terminal_run_refuses_a_retry_with_four(cli, graph_file):
    _, started = cli("start", "--graph", graph_file, "--thread", "t1", "--resource", "user")
    cli(
        "complete", "--run", started["id"], "--step", "research",
        "--result", '{"text":"x","signal":{"length":"short"}}',
    )
    cli("complete", "--run", started["id"], "--step", "seo", "--result", '{"text":"x"}')
    cli("complete", "--run", started["id"], "--step", "tone", "--result", '{"text":"x"}')
    cli("complete", "--run", started["id"], "--step", "quick", "--result", '{"text":"x"}')

    code, payload = cli("retry", "--run", started["id"], "--step", "quick")

    assert code == 4
    assert "done" in payload["error"]


def test_memory_round_trips_through_the_cli(cli):
    code, remembered = cli(
        "remember", "--thread", "t1", "--resource", "user",
        "--working-memory", '{"tone":"plain"}', "--observation", "prefers short drafts",
    )
    assert code == 0
    assert remembered["working_memory"] == {"tone": "plain"}

    code, recalled = cli("recall", "--thread", "t1", "--resource", "user")
    assert code == 0
    assert recalled["observations"][0]["text"] == "prefers short drafts"


def test_render_prints_ascii_and_mermaid(cli, graph_file):
    code, ascii_payload = cli("render", "--graph", graph_file, "--format", "ascii")
    assert code == 0
    assert "research" in ascii_payload["text"]
    assert ascii_payload["text"].splitlines()[0].startswith("then")

    _, mermaid = cli("render", "--graph", graph_file, "--format", "mermaid")
    assert mermaid["text"].startswith("flowchart TD")


def test_export_writes_a_file(cli, graph_file, tmp_path):
    _, started = cli("start", "--graph", graph_file, "--thread", "t1", "--resource", "user")
    out = tmp_path / "run.json"

    code, payload = cli("export", "--run", started["id"], "--out", str(out))

    assert code == 0
    assert json.loads(out.read_text(encoding="utf-8"))["id"] == started["id"]
    assert payload["exported"].endswith("run.json")


def test_doctor_reports_a_writable_root(cli):
    code, payload = cli("doctor")

    assert code == 0
    assert payload["writable"] is True
    assert payload["version"] == "2.0.0"


def test_the_swarm_drives_a_debate_to_consensus(cli, tmp_path):
    _, opened = cli(
        "swarm", "open", "--goal", "compare the two options and decide",
        "--thread", "t1", "--resource", "user",
    )
    assert opened["graph_id"].startswith("debate:")

    code, batch = cli("swarm", "batch", "--run", opened["id"])
    assert code == 0
    assert {step["id"] for step in batch["batch"]} == {"case-a", "case-b", "case-c"}
    assert "Independent lane" in batch["batch"][0]["context"]

    cli("swarm", "record", "--run", opened["id"], "--step", "case-a", "--result", '{"text":"short"}')
    cli("swarm", "record", "--run", opened["id"], "--step", "case-b", "--result", '{"text":"short"}')
    cli("swarm", "record", "--run", opened["id"], "--step", "case-c", "--result", '{"text":"long"}')

    code, verdict = cli("swarm", "consensus", "--run", opened["id"], "--group", "debate")
    assert code == 0
    assert verdict["winner"] == "short"
    assert verdict["dissent"] == ["long"]

    _, recap = cli("swarm", "recap", "--run", opened["id"])
    assert "debate" in recap["recap"]


def test_swarm_plan_writes_a_graph(cli, tmp_path):
    out = tmp_path / "plan.json"

    code, payload = cli("swarm", "plan", "--goal", "audit the security of this module", "--out", str(out))

    assert code == 0
    assert payload["template"] == "review-sweep"
    assert json.loads(out.read_text(encoding="utf-8"))["id"].startswith("review-sweep:")


def test_an_unknown_template_exits_two(cli):
    code, payload = cli("swarm", "plan", "--goal", "anything", "--template", "telepathy")

    assert code == 2
    assert "unknown template" in payload["error"]


def test_completing_a_swarm_run_through_complete_still_feeds_the_swarm(cli):
    _, opened = cli(
        "swarm", "open", "--goal", "answer this", "--thread", "t1", "--resource", "user",
        "--template", "blank",
    )

    code, _ = cli("complete", "--run", opened["id"], "--step", "answer", "--result", '{"text":"done"}')

    assert code == 0
    _, verdict = cli("swarm", "verdict", "--run", opened["id"])
    assert verdict["status"] == "done"
    assert verdict["artifacts"] == 1
    _, doctor = cli("doctor")
    assert "blank" in doctor["policy"]


def test_root_flag_beats_the_environment(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MASTRA_ROOT", str(tmp_path / "decoy"))
    chosen = tmp_path / "chosen"

    code = main(["--root", str(chosen), "doctor"])

    assert code == 0
    assert json.loads(capsys.readouterr().out)["root"] == str(chosen)


def test_pretty_after_the_subcommand_is_honoured(tmp_path, capsys):
    code = main(["--root", str(tmp_path / "store"), "doctor", "--pretty"])

    assert code == 0
    assert "\n  " in capsys.readouterr().out
