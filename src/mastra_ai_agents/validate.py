"""Structural validation for graph documents (schema v2).

Validation is deliberately a report rather than a gate: a graph author gets
every problem in one pass, each prefixed with the JSON path that caused it, so
fixing a document is one edit round instead of one round per typo.
"""

from __future__ import annotations

from typing import Any


class GraphError(ValueError):
    """A graph document that cannot be run.

    Carries the individual problems as well as their joined message so callers
    can render them as a list instead of grepping one long string.
    """

    def __init__(self, problems: list[str]) -> None:
        self.problems = list(problems)
        super().__init__("; ".join(self.problems))


def validate_graph(raw: Any) -> list[str]:
    """Return every structural problem in `raw`; an empty list means runnable.

    Accepts anything, because the input often comes straight from JSON on disk
    or from a model, and a validator that raises tells the caller nothing about
    what to fix.
    """
    problems: list[str] = []
    if not isinstance(raw, dict):
        return [f"$: expected an object, got {type(raw).__name__}"]

    if not _is_nonempty_str(raw.get("id")):
        problems.append("id: expected a non-empty string")

    if "roster" in raw and not isinstance(raw["roster"], dict):
        problems.append("roster: expected an object")

    chain = raw.get("chain")
    if not isinstance(chain, list) or not chain:
        problems.append("chain: expected a non-empty list")
        return problems

    seen: dict[str, str] = {}
    for index, node in enumerate(chain):
        _check_node(node, f"chain[{index}]", seen, problems)

    return problems


_OPS = ("then", "parallel", "branch", "foreach", "loop")


def _check_node(node: Any, path: str, seen: dict[str, str], problems: list[str]) -> None:
    if not isinstance(node, dict):
        problems.append(f"{path}: expected an object, got {type(node).__name__}")
        return

    op = node.get("op")
    if not _is_nonempty_str(op):
        problems.append(f"{path}.op: expected a non-empty string")
        return
    if op not in _OPS:
        problems.append(f"{path}.op: unknown op {op!r}")
        return

    if op == "then":
        _check_then(node, path, seen, problems)
    elif op == "parallel":
        _check_step_list(node, path, seen, problems)
    elif op == "branch":
        _check_branch(node, path, seen, problems)
    elif op == "foreach":
        _check_foreach(node, path, seen, problems)
    elif op == "loop":
        _check_loop(node, path, seen, problems)


def _check_then(node: dict[str, Any], path: str, seen: dict[str, str], problems: list[str]) -> None:
    _check_step_node(node.get("step"), f"{path}.step", seen, problems)


def _check_loop(
    node: dict[str, Any], path: str, seen: dict[str, str], problems: list[str]
) -> None:
    _check_step_list(node, path, seen, problems)
    until = node.get("until")
    if not isinstance(until, dict) or not until:
        problems.append(f"{path}.until: expected a non-empty object")
    if not _is_int_at_least(node.get("max_iterations"), 1):
        problems.append(f"{path}.max_iterations: expected an int >= 1")


def _check_foreach(
    node: dict[str, Any], path: str, seen: dict[str, str], problems: list[str]
) -> None:
    if not _is_nonempty_str(node.get("over")):
        problems.append(f"{path}.over: expected a non-empty string")
    _check_step_list(node, path, seen, problems)
    if "max_parallel" in node and not _is_int_at_least(node["max_parallel"], 1):
        problems.append(f"{path}.max_parallel: expected an int >= 1")


def _check_branch(
    node: dict[str, Any], path: str, seen: dict[str, str], problems: list[str]
) -> None:
    cases = node.get("cases")
    if not isinstance(cases, list) or not cases:
        problems.append(f"{path}.cases: expected a non-empty list")
    else:
        for index, case in enumerate(cases):
            case_path = f"{path}.cases[{index}]"
            if not isinstance(case, dict):
                problems.append(f"{case_path}: expected an object")
                continue
            when = case.get("when")
            if not isinstance(when, dict) or not when:
                problems.append(f"{case_path}.when: expected a non-empty object")
            _check_step_node(case.get("step"), f"{case_path}.step", seen, problems)

    default = node.get("default")
    if default is not None:
        _check_step_node(default, f"{path}.default", seen, problems)


def _check_step_list(
    node: dict[str, Any], path: str, seen: dict[str, str], problems: list[str]
) -> None:
    steps = node.get("steps")
    if not isinstance(steps, list) or not steps:
        problems.append(f"{path}.steps: expected a non-empty list")
        return
    for index, step in enumerate(steps):
        _check_step_node(step, f"{path}.steps[{index}]", seen, problems)


def _check_step_node(
    raw_step: Any, path: str, seen: dict[str, str], problems: list[str]
) -> None:
    if not isinstance(raw_step, dict):
        problems.append(f"{path}: expected an object")
        return
    _check_step(raw_step, path, seen, problems)


_STEP_FIELDS = ("id", "agent", "instruction")


def _check_step(step: dict[str, Any], path: str, seen: dict[str, str], problems: list[str]) -> None:
    for field in _STEP_FIELDS:
        if not _is_nonempty_str(step.get(field)):
            problems.append(f"{path}.{field}: expected a non-empty string")

    step_id = step.get("id")
    if _is_nonempty_str(step_id):
        if step_id in seen:
            problems.append(f"{path}.id: duplicate step id {step_id!r}")
        else:
            seen[step_id] = path

    if "retries" in step and not _is_int_at_least(step["retries"], 0):
        problems.append(f"{path}.retries: expected an int >= 0")
    if "timeout_s" in step and not _is_int_at_least(step["timeout_s"], 1):
        problems.append(f"{path}.timeout_s: expected an int >= 1")
    if "meta" in step and not isinstance(step["meta"], dict):
        problems.append(f"{path}.meta: expected an object")


def _is_nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value)


def _is_int_at_least(value: Any, minimum: int) -> bool:
    """Bools are ints in Python, but `"retries": true` is a graph bug, not one retry."""
    return isinstance(value, int) and not isinstance(value, bool) and value >= minimum
