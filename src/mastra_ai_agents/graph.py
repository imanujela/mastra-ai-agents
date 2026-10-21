"""Graph parsing for the orchestration runtime.

`validate` decides whether a document is well formed; this module turns a well
formed one into the object the runtime actually walks. The graph a caller hands
in is theirs to keep, so parsing hands back a copy they can annotate freely.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from copy import deepcopy
from typing import Any

from mastra_ai_agents.validate import GraphError, validate_graph

__all__ = ["iter_ops", "parse_graph", "step_ids"]


def parse_graph(raw: dict[str, Any]) -> dict[str, Any]:
    """Return a runnable graph, or raise `GraphError` with every problem found.

    The result is a deep copy: the engine and renderers annotate nodes, and the
    caller's document (often a fixture or the parsed contents of a file they
    still hold) must not change underneath them.
    """
    problems = validate_graph(raw)
    if problems:
        raise GraphError(problems)

    graph = deepcopy(raw)
    for node in graph["chain"]:
        _fill_node_defaults(node)
    return graph


def iter_ops(chain: Iterable[dict[str, Any]]) -> Iterator[dict[str, Any]]:
    """Walk the chain top to bottom, yielding whole op nodes.

    Nodes stay whole because every consumer needs the op together with its
    payload; splitting them into (op, data) pairs would just force reassembly.
    """
    yield from chain


def step_ids(chain: Iterable[dict[str, Any]]) -> list[str]:
    """Every declared step id, in reading order, nested blocks included.

    These are base ids. `#<i>` suffixes are runtime expansion of foreach
    copies, so planning and rendering can talk about a graph before it has any
    items to fan out over.
    """
    return [step["id"] for node in chain for step in _steps_in(node)]


def _steps_in(node: dict[str, Any]) -> Iterator[dict[str, Any]]:
    op = node["op"]
    if op == "then":
        yield node["step"]
    elif op == "branch":
        for case in node["cases"]:
            yield case["step"]
        if node.get("default") is not None:
            yield node["default"]
    elif op in ("parallel", "foreach", "loop"):
        yield from node["steps"]


def _fill_node_defaults(node: dict[str, Any]) -> None:
    """Materialise step defaults so every consumer reads one shape.

    Validation has already established the op and its nested steps, so this
    walk deliberately re-checks none of it.
    """
    op = node["op"]
    if op == "then":
        _fill_step_defaults(node["step"])
    elif op == "branch":
        for case in node["cases"]:
            _fill_step_defaults(case["step"])
        if node.get("default") is not None:
            _fill_step_defaults(node["default"])
    elif op in ("parallel", "foreach", "loop"):
        for step in node["steps"]:
            _fill_step_defaults(step)


def _fill_step_defaults(step: dict[str, Any]) -> None:
    step.setdefault("retries", 0)
    step.setdefault("meta", {})
