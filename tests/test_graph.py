"""Parsing is the one gate between JSON on disk and a runnable graph.

The tests care about the promises the rest of the runtime leans on: a bad graph
fails loudly with all of its problems, a parsed graph is safe to mutate and
carries its step defaults, and step ids can be listed before any run has
expanded foreach copies.
"""

import pytest

from mastra_ai_agents.graph import iter_ops, parse_graph, step_ids
from mastra_ai_agents.validate import GraphError


def test_parse_graph_raises_graph_error_with_every_problem():
    with pytest.raises(GraphError) as excinfo:
        parse_graph({"id": "", "chain": []})

    assert excinfo.value.problems == [
        "id: expected a non-empty string",
        "chain: expected a non-empty list",
    ]
    assert "chain: expected a non-empty list" in str(excinfo.value)


def test_parse_graph_returns_a_deep_copy():
    graph = {
        "id": "g",
        "chain": [
            {
                "op": "then",
                "step": {
                    "id": "a",
                    "agent": "w",
                    "instruction": "go",
                    "meta": {"tags": ["one"]},
                },
            }
        ],
    }

    parsed = parse_graph(graph)
    parsed["chain"][0]["step"]["instruction"] = "changed"
    parsed["chain"][0]["step"]["meta"]["tags"].append("two")

    assert graph["chain"][0]["step"]["instruction"] == "go"
    assert graph["chain"][0]["step"]["meta"]["tags"] == ["one"]


def test_parse_graph_materializes_step_defaults():
    graph = {
        "id": "g",
        "chain": [
            {"op": "then", "step": {"id": "a", "agent": "w", "instruction": "go"}},
            {
                "op": "parallel",
                "steps": [{"id": "b", "agent": "w", "instruction": "go"}],
            },
        ],
    }

    parsed = parse_graph(graph)

    assert parsed["chain"][0]["step"]["retries"] == 0
    assert parsed["chain"][0]["step"]["meta"] == {}
    assert parsed["chain"][1]["steps"][0]["retries"] == 0
    assert parsed["chain"][1]["steps"][0]["meta"] == {}
    assert "retries" not in graph["chain"][0]["step"]


def test_iter_ops_yields_each_node_in_chain_order():
    first = {"op": "then", "step": {"id": "a", "agent": "w", "instruction": "go"}}
    second = {"op": "parallel", "steps": [{"id": "b", "agent": "w", "instruction": "go"}]}
    third = {
        "op": "loop",
        "steps": [{"id": "c", "agent": "w", "instruction": "go"}],
        "until": {"done": True},
        "max_iterations": 2,
    }

    assert list(iter_ops([first, second, third])) == [first, second, third]


def test_step_ids_lists_branch_cases_and_default():
    chain = [
        {"op": "then", "step": {"id": "a", "agent": "w", "instruction": "go"}},
        {
            "op": "branch",
            "cases": [
                {"when": {"x": 1}, "step": {"id": "b", "agent": "w", "instruction": "go"}},
                {"when": {"x": 2}, "step": {"id": "c", "agent": "w", "instruction": "go"}},
            ],
            "default": {"id": "d", "agent": "w", "instruction": "go"},
        },
    ]

    assert step_ids(chain) == ["a", "b", "c", "d"]


def test_step_ids_uses_base_ids_for_foreach_and_loop_blocks():
    chain = [
        {
            "op": "foreach",
            "over": "topics",
            "steps": [
                {"id": "draft", "agent": "w", "instruction": "Draft {{item}}"},
                {"id": "check", "agent": "e", "instruction": "Check"},
            ],
            "max_parallel": 2,
        },
        {
            "op": "loop",
            "steps": [{"id": "revise", "agent": "e", "instruction": "Revise"}],
            "until": {"done": True},
            "max_iterations": 2,
        },
    ]

    assert step_ids(chain) == ["draft", "check", "revise"]


def test_step_ids_walks_a_parsed_full_graph_in_declaration_order():
    graph = {
        "id": "content",
        "chain": [
            {"op": "then", "step": {"id": "research", "agent": "r", "instruction": "Go"}},
            {
                "op": "parallel",
                "steps": [
                    {"id": "seo", "agent": "a", "instruction": "Go"},
                    {"id": "tone", "agent": "a", "instruction": "Go"},
                ],
            },
            {
                "op": "branch",
                "cases": [
                    {
                        "when": {"length": "long"},
                        "step": {"id": "deep", "agent": "w", "instruction": "Go"},
                    }
                ],
                "default": {"id": "quick", "agent": "w", "instruction": "Go"},
            },
            {
                "op": "foreach",
                "over": "topics",
                "steps": [{"id": "draft", "agent": "w", "instruction": "Draft {{item}}"}],
            },
            {
                "op": "loop",
                "steps": [{"id": "revise", "agent": "e", "instruction": "Revise"}],
                "until": {"approved": True},
                "max_iterations": 3,
            },
        ],
    }

    parsed = parse_graph(graph)

    assert step_ids(parsed["chain"]) == [
        "research",
        "seo",
        "tone",
        "deep",
        "quick",
        "draft",
        "revise",
    ]
