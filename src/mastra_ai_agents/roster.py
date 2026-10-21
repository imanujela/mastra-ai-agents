"""Roster parsing and per-step identity resolution.

The roster decides which agents keep their own memory. A worker without
``own_memory`` is a pure function of the parent thread, so it must receive the
run's thread and resource; an agent with ``own_memory`` owns its identity and
must not be pointed at the orchestrator's thread.
"""

from __future__ import annotations

from typing import Any

from .types import Run, Step


def parse_roster(raw: dict[str, dict[str, Any]] | None) -> dict[str, dict[str, Any]]:
    """Return a validated copy of the roster, naming the agent at fault."""
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("roster must be a mapping of agent name to config")
    roster: dict[str, dict[str, Any]] = {}
    for agent, config in raw.items():
        name = str(agent)
        if not name:
            raise ValueError("roster agent names must be non-empty")
        if not isinstance(config, dict):
            raise ValueError(f"roster entry for agent {name!r} must be an object")
        if "own_memory" in config and not isinstance(config["own_memory"], bool):
            raise ValueError(f"roster entry for agent {name!r}: own_memory must be a bool")
        roster[name] = dict(config)
    return roster


def resolve_step(
    raw_step: dict[str, Any], run: Run, roster: dict[str, dict[str, Any]]
) -> Step:
    """Bind a step to the run's thread unless its agent owns its memory."""
    agent = str(raw_step["agent"])
    own_memory = bool(roster.get(agent, {}).get("own_memory", False))
    return Step(
        id=str(raw_step["id"]),
        agent=agent,
        instruction=str(raw_step["instruction"]),
        memory_thread=None if own_memory else run.thread,
        resource=None if own_memory else run.resource,
        retries=int(raw_step.get("retries", 0)),
        timeout_s=raw_step.get("timeout_s"),
        meta=dict(raw_step.get("meta") or {}),
    )
