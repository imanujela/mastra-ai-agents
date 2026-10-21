"""A graph validator reports every problem with its path, never just the first.

The messages are the contract: they are what a graph author sees when a run
refuses to start, so the tests pin the path prefixes rather than just "invalid".
"""

from mastra_ai_agents.validate import validate_graph


def test_missing_top_level_id_is_reported():
    problems = validate_graph(
        {"chain": [{"op": "then", "step": {"id": "a", "agent": "w", "instruction": "go"}}]}
    )

    assert problems == ["id: expected a non-empty string"]


def test_unknown_op_is_reported_with_its_name():
    problems = validate_graph({"id": "g", "chain": [{"op": "fanout"}]})

    assert problems == ["chain[0].op: unknown op 'fanout'"]


def test_missing_op_and_non_object_nodes_are_reported():
    problems = validate_graph({"id": "g", "chain": [{}, "then"]})

    assert problems == [
        "chain[0].op: expected a non-empty string",
        "chain[1]: expected an object, got str",
    ]


def test_then_requires_its_step_object():
    problems = validate_graph({"id": "g", "chain": [{"op": "then"}]})

    assert problems == ["chain[0].step: expected an object"]


def test_step_requires_id_agent_and_instruction():
    problems = validate_graph(
        {"id": "g", "chain": [{"op": "then", "step": {"instruction": ""}}]}
    )

    assert problems == [
        "chain[0].step.id: expected a non-empty string",
        "chain[0].step.agent: expected a non-empty string",
        "chain[0].step.instruction: expected a non-empty string",
    ]


def test_step_options_must_be_well_typed():
    base = {"agent": "w", "instruction": "go"}
    problems = validate_graph(
        {
            "id": "g",
            "chain": [
                {"op": "then", "step": {**base, "id": "a", "retries": True}},
                {"op": "then", "step": {**base, "id": "b", "timeout_s": 0}},
                {"op": "then", "step": {**base, "id": "c", "meta": []}},
            ],
        }
    )

    assert problems == [
        "chain[0].step.retries: expected an int >= 0",
        "chain[1].step.timeout_s: expected an int >= 1",
        "chain[2].step.meta: expected an object",
    ]


def test_parallel_needs_a_non_empty_step_list():
    problems = validate_graph({"id": "g", "chain": [{"op": "parallel", "steps": []}]})

    assert problems == ["chain[0].steps: expected a non-empty list"]


def test_branch_validates_cases_when_and_default():
    problems = validate_graph(
        {
            "id": "g",
            "chain": [
                {"op": "branch", "cases": []},
                {
                    "op": "branch",
                    "cases": [
                        {
                            "when": {},
                            "step": {"id": "a", "agent": "w", "instruction": "go"},
                        },
                        {"when": {"length": "long"}},
                    ],
                    "default": "nope",
                },
            ],
        }
    )

    assert problems == [
        "chain[0].cases: expected a non-empty list",
        "chain[1].cases[0].when: expected a non-empty object",
        "chain[1].cases[1].step: expected an object",
        "chain[1].default: expected an object",
    ]


def test_foreach_requires_over_and_a_positive_parallel_cap():
    problems = validate_graph(
        {
            "id": "g",
            "chain": [{"op": "foreach", "over": "", "steps": [], "max_parallel": 0}],
        }
    )

    assert problems == [
        "chain[0].over: expected a non-empty string",
        "chain[0].steps: expected a non-empty list",
        "chain[0].max_parallel: expected an int >= 1",
    ]


def test_loop_requires_until_and_a_positive_iteration_cap():
    problems = validate_graph(
        {
            "id": "g",
            "chain": [{"op": "loop", "steps": [], "until": {}, "max_iterations": 0}],
        }
    )

    assert problems == [
        "chain[0].steps: expected a non-empty list",
        "chain[0].until: expected a non-empty object",
        "chain[0].max_iterations: expected an int >= 1",
    ]


def test_duplicate_step_ids_are_caught_across_nested_blocks():
    problems = validate_graph(
        {
            "id": "g",
            "chain": [
                {
                    "op": "parallel",
                    "steps": [{"id": "seo", "agent": "a", "instruction": "x"}],
                },
                {
                    "op": "branch",
                    "cases": [
                        {
                            "when": {"k": 1},
                            "step": {"id": "seo", "agent": "b", "instruction": "y"},
                        }
                    ],
                    "default": {"id": "tone", "agent": "c", "instruction": "z"},
                },
                {
                    "op": "loop",
                    "steps": [{"id": "tone", "agent": "d", "instruction": "w"}],
                    "until": {"done": True},
                    "max_iterations": 2,
                },
            ],
        }
    )

    assert problems == [
        "chain[1].cases[0].step.id: duplicate step id 'seo'",
        "chain[2].steps[0].id: duplicate step id 'tone'",
    ]


def test_roster_must_be_an_object_when_present():
    problems = validate_graph(
        {
            "id": "g",
            "chain": [{"op": "then", "step": {"id": "a", "agent": "w", "instruction": "go"}}],
            "roster": [],
        }
    )

    assert problems == ["roster: expected an object"]


def test_non_object_graph_is_a_problem_not_an_exception():
    assert validate_graph([]) == ["$: expected an object, got list"]


def test_full_v2_graph_has_no_problems():
    graph = {
        "id": "content",
        "roster": {"writer": {"agent": "hermes"}},
        "chain": [
            {
                "op": "then",
                "step": {
                    "id": "research",
                    "agent": "researcher",
                    "instruction": "Find sources.",
                    "retries": 1,
                    "timeout_s": 60,
                    "meta": {"tags": ["web"]},
                },
            },
            {
                "op": "parallel",
                "steps": [
                    {"id": "seo", "agent": "analyst", "instruction": "SEO"},
                    {"id": "tone", "agent": "analyst", "instruction": "Tone"},
                ],
            },
            {
                "op": "branch",
                "cases": [
                    {
                        "when": {"length": "long"},
                        "step": {"id": "deep", "agent": "writer", "instruction": "Long"},
                    }
                ],
                "default": {"id": "quick", "agent": "writer", "instruction": "Short"},
            },
            {
                "op": "foreach",
                "over": "topics",
                "steps": [
                    {"id": "draft", "agent": "writer", "instruction": "Draft {{item}}"}
                ],
                "max_parallel": 2,
            },
            {
                "op": "loop",
                "steps": [{"id": "revise", "agent": "editor", "instruction": "Revise"}],
                "until": {"approved": True},
                "max_iterations": 3,
            },
        ],
    }

    assert validate_graph(graph) == []


def test_v1_graph_without_the_nested_ops_is_still_valid():
    graph = {
        "id": "content",
        "chain": [
            {
                "op": "then",
                "step": {"id": "research", "agent": "researcher", "instruction": "Find sources."},
            },
            {
                "op": "parallel",
                "steps": [
                    {"id": "seo", "agent": "analyst", "instruction": "SEO"},
                    {"id": "tone", "agent": "analyst", "instruction": "Tone"},
                ],
            },
            {
                "op": "branch",
                "cases": [
                    {
                        "when": {"length": "long"},
                        "step": {"id": "deep", "agent": "writer", "instruction": "Long"},
                    }
                ],
            },
        ],
    }

    assert validate_graph(graph) == []
