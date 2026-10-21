"""Renderers are the read-only window into a graph: Mermaid for docs, ASCII for terminals."""

import json
from pathlib import Path

from mastra_ai_agents.render import run_mermaid, to_ascii, to_mermaid
from mastra_ai_agents.types import FAILED, RUNNING, Run, Step

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def content_graph() -> dict:
    return json.loads((EXAMPLES / "content.json").read_text(encoding="utf-8"))


def test_starts_with_flowchart_td():
    assert to_mermaid(content_graph()).startswith("flowchart TD")


def test_every_step_gets_exactly_one_node():
    text = to_mermaid(content_graph())

    for step_id in ("research", "seo", "tone", "deep", "quick"):
        assert text.count(f'  {step_id}["') == 1


def test_node_label_shows_id_agent_and_instruction():
    text = to_mermaid(content_graph())

    assert "research · researcher" in text
    assert "Find three sources." in text


def test_parallel_steps_fan_out_from_the_previous_node():
    text = to_mermaid(content_graph())

    assert "research --> seo" in text
    assert "research --> tone" in text


def test_branch_edges_are_labelled_per_case():
    text = to_mermaid(content_graph())

    assert "seo -->|when length=long| deep" in text
    assert "tone -->|when length=long| deep" in text
    assert "seo -->|when length=short| quick" in text


def test_default_edge_only_when_supplied():
    graph = {
        "id": "g",
        "chain": [
            {"op": "then", "step": {"id": "plan", "agent": "a", "instruction": "Plan"}},
            {
                "op": "branch",
                "cases": [{"when": {"length": "long"}, "step": {"id": "deep", "agent": "w", "instruction": "Long"}}],
            },
        ],
    }
    assert "default" not in to_mermaid(graph)

    graph["chain"][1]["default"] = {"id": "fallback", "agent": "w", "instruction": "Fallback"}
    text = to_mermaid(graph)

    assert "plan -->|default| fallback" in text


def test_foreach_renders_one_representative_chain():
    graph = {
        "id": "g",
        "chain": [
            {"op": "then", "step": {"id": "plan", "agent": "a", "instruction": "Plan"}},
            {
                "op": "foreach",
                "over": "items",
                "steps": [
                    {"id": "extract", "agent": "b", "instruction": "Extract {{item}}"},
                    {"id": "summarize", "agent": "c", "instruction": "Summarize"},
                ],
            },
        ],
    }
    text = to_mermaid(graph)

    assert 'subgraph sub_foreach_items["foreach over items"]' in text
    assert '    extract_i["extract#i · b — Extract {{item}}"]' in text
    assert "    extract_i --> summarize_i" in text
    assert "1 representative chain" in text
    assert "plan --> sub_foreach_items" in text


def test_loop_subgraph_label_and_chain():
    graph = {
        "id": "g",
        "chain": [
            {"op": "then", "step": {"id": "plan", "agent": "a", "instruction": "Plan"}},
            {
                "op": "loop",
                "steps": [
                    {"id": "draft", "agent": "w", "instruction": "Draft"},
                    {"id": "check", "agent": "e", "instruction": "Check"},
                ],
                "until": {"length": "short"},
                "max_iterations": 3,
            },
        ],
    }
    text = to_mermaid(graph)

    assert 'subgraph sub_loop_1["loop until length=short max 3"]' in text
    assert "    draft --> check" in text
    assert "plan --> sub_loop_1" in text


def test_ids_are_sanitized():
    graph = {
        "id": "g",
        "chain": [
            {"op": "then", "step": {"id": "draft.v2", "agent": "a", "instruction": "A"}},
            {"op": "then", "step": {"id": "two-words here", "agent": "b", "instruction": "B"}},
            {"op": "then", "step": {"id": "3blindmice", "agent": "c", "instruction": "C"}},
        ],
    }
    text = to_mermaid(graph)

    assert '  draft_v2["draft.v2 · ' in text
    assert '  two_words_here["two-words here · ' in text
    assert '  n_3blindmice["3blindmice · ' in text


def test_id_collisions_get_numeric_suffix():
    graph = {
        "id": "g",
        "chain": [
            {"op": "then", "step": {"id": "a.b", "agent": "x", "instruction": "A"}},
            {"op": "then", "step": {"id": "a-b", "agent": "y", "instruction": "B"}},
        ],
    }
    text = to_mermaid(graph)

    assert '  a_b["a.b · ' in text
    assert '  a_b_2["a-b · ' in text
    assert "a_b --> a_b_2" in text


def test_instruction_quotes_and_newlines_cannot_break_mermaid():
    graph = {
        "id": "g",
        "chain": [
            {
                "op": "then",
                "step": {"id": "talk", "agent": "a", "instruction": 'Say "hi"\nthen stop'},
            }
        ],
    }
    text = to_mermaid(graph)
    node_line = next(line for line in text.splitlines() if line.lstrip().startswith("talk["))

    assert 'Say "hi"' not in node_line
    assert "Say #quot;hi#quot; then stop" in node_line
    assert node_line.count('"') == 2


def test_long_instruction_is_truncated_to_sixty_chars():
    graph = {
        "id": "g",
        "chain": [
            {"op": "then", "step": {"id": "long", "agent": "a", "instruction": "x" * 80}},
        ],
    }
    text = to_mermaid(graph)

    assert "x" * 60 in text
    assert "x" * 61 not in text


def test_to_mermaid_is_deterministic():
    assert to_mermaid(content_graph()) == to_mermaid(content_graph())


def three_step_chain() -> list[dict]:
    return [
        {"op": "then", "step": {"id": "a", "agent": "x", "instruction": "A"}},
        {"op": "then", "step": {"id": "b", "agent": "x", "instruction": "B"}},
        {"op": "then", "step": {"id": "c", "agent": "x", "instruction": "C"}},
    ]


def test_run_mermaid_reports_status_and_progress():
    run = Run(
        id="r1",
        chain=three_step_chain(),
        status=RUNNING,
        outputs={"a": {"text": "done"}},
        ready=[Step(id="b", agent="x", instruction="B")],
    )
    text = run_mermaid(run)

    assert "%% run r1 running 1/3" in text
    assert text.startswith("flowchart TD")


def test_run_mermaid_marks_done_active_and_pending():
    run = Run(
        id="r1",
        chain=three_step_chain(),
        status=RUNNING,
        outputs={"a": {"text": "done"}},
        ready=[Step(id="b", agent="x", instruction="B")],
    )
    text = run_mermaid(run)

    assert 'a["a · x — A"]:::done' in text
    assert 'b["b · x — B"]:::active' in text
    assert 'c["c · x — C"]:::pending' in text


def test_run_mermaid_marks_failed_steps_on_a_failed_run():
    run = Run(id="r2", chain=three_step_chain(), status=FAILED, outputs={"a": {"text": "done"}})
    text = run_mermaid(run)

    assert "%% run r2 failed 1/3" in text
    assert 'a["a · x — A"]:::done' in text
    assert 'b["b · x — B"]:::failed' in text
    assert 'c["c · x — C"]:::failed' in text


def test_run_mermaid_treats_foreach_id_variants_as_done():
    run = Run(
        id="r3",
        chain=[
            {
                "op": "foreach",
                "over": "items",
                "steps": [{"id": "extract", "agent": "b", "instruction": "Extract {{item}}"}],
            }
        ],
        outputs={"extract#0": {"text": "one"}, "extract#1": {"text": "two"}},
    )
    text = run_mermaid(run)

    assert "]:::done" in text
    assert "%% run r3 running 1/1" in text


def test_run_mermaid_emits_class_definitions():
    text = run_mermaid(Run(id="r4", chain=three_step_chain()))

    for name in ("done", "active", "pending", "failed"):
        assert f"classDef {name} " in text


def test_ascii_renders_then_and_parallel():
    lines = to_ascii(content_graph()).splitlines()

    assert lines[0] == "then  research (researcher)"
    assert "parallel (2 steps)" in lines
    assert "  seo (analyst)" in lines
    assert "  tone (analyst)" in lines


def test_ascii_indents_branch_cases_by_depth():
    lines = to_ascii(content_graph()).splitlines()
    header = lines.index("branch 2 cases")

    assert lines[header + 1] == "  when length=long"
    assert lines[header + 2] == "    deep (writer)"


def test_ascii_covers_all_five_ops():
    graph = {
        "id": "g",
        "chain": [
            {"op": "then", "step": {"id": "plan", "agent": "a", "instruction": "Plan"}},
            {
                "op": "parallel",
                "steps": [
                    {"id": "seo", "agent": "b", "instruction": "SEO"},
                    {"id": "tone", "agent": "b", "instruction": "Tone"},
                ],
            },
            {
                "op": "branch",
                "cases": [
                    {"when": {"length": "long"}, "step": {"id": "deep", "agent": "w", "instruction": "Long"}}
                ],
            },
            {
                "op": "foreach",
                "over": "items",
                "steps": [
                    {"id": "extract", "agent": "r", "instruction": "Extract"},
                    {"id": "summarize", "agent": "s", "instruction": "Summarize"},
                ],
            },
            {
                "op": "loop",
                "steps": [
                    {"id": "draft", "agent": "w", "instruction": "Draft"},
                    {"id": "check", "agent": "e", "instruction": "Check"},
                ],
                "until": {"length": "short"},
                "max_iterations": 3,
            },
        ],
    }

    assert to_ascii(graph).splitlines() == [
        "then  plan (a)",
        "parallel (2 steps)",
        "  seo (b)",
        "  tone (b)",
        "branch 1 cases",
        "  when length=long",
        "    deep (w)",
        "foreach over items (2 steps each)",
        "  extract (r)",
        "  summarize (s)",
        "loop until length=short max 3 (2 steps)",
        "  draft (w)",
        "  check (e)",
    ]


def test_ascii_has_no_box_drawing_or_trailing_spaces():
    text = to_ascii(content_graph())

    assert not any(char in text for char in "┌┐└┘│├┤─┬┴┼")
    for line in text.splitlines():
        assert line == line.rstrip()

