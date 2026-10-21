"""Fixed data contract for the runtime.

Every module imports these types. Nothing else may redefine them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

RUNNING = "running"
DONE = "done"
BAILED = "bailed"
ABORTED = "aborted"
FAILED = "failed"

TERMINAL = frozenset({DONE, BAILED, ABORTED, FAILED})


def utc_now() -> str:
    """Timestamp used by runs, events and memory: UTC, second precision, ISO 8601."""
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass
class Step:
    """One unit of work for one worker (a Hermes sub-agent)."""

    id: str
    agent: str
    instruction: str
    memory_thread: str | None = None
    resource: str | None = None
    retries: int = 0
    timeout_s: int | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "agent": self.agent,
            "instruction": self.instruction,
            "memory_thread": self.memory_thread,
            "resource": self.resource,
            "retries": self.retries,
            "timeout_s": self.timeout_s,
            "meta": dict(self.meta),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Step:
        return cls(
            id=str(raw["id"]),
            agent=str(raw["agent"]),
            instruction=str(raw["instruction"]),
            memory_thread=raw.get("memory_thread"),
            resource=raw.get("resource"),
            retries=int(raw.get("retries", 0)),
            timeout_s=raw.get("timeout_s"),
            meta=dict(raw.get("meta") or {}),
        )


@dataclass
class Run:
    """A saved supervisor run. Serializable both ways, no private state."""

    id: str
    ready: list[Step] = field(default_factory=list)
    status: str = RUNNING
    outputs: dict[str, Any] = field(default_factory=dict)
    signal: dict[str, Any] = field(default_factory=dict)
    thread: str = ""
    resource: str = ""
    chain: list[dict[str, Any]] = field(default_factory=list)
    index: int = 0
    pending: list[str] = field(default_factory=list)
    iterations: dict[str, int] = field(default_factory=dict)
    attempts: dict[str, int] = field(default_factory=dict)
    graph_id: str = ""
    roster: dict[str, Any] = field(default_factory=dict)
    note: str = ""
    created_at: str = ""
    updated_at: str = ""

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL

    def ready_ids(self) -> list[str]:
        return [step.id for step in self.ready]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "graph_id": self.graph_id,
            "roster": dict(self.roster),
            "status": self.status,
            "ready": [step.to_dict() for step in self.ready],
            "outputs": dict(self.outputs),
            "signal": dict(self.signal),
            "thread": self.thread,
            "resource": self.resource,
            "chain": list(self.chain),
            "index": self.index,
            "pending": list(self.pending),
            "iterations": dict(self.iterations),
            "attempts": dict(self.attempts),
            "note": self.note,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Run:
        return cls(
            id=str(raw["id"]),
            ready=[Step.from_dict(step) for step in raw.get("ready") or []],
            status=str(raw.get("status", RUNNING)),
            outputs=dict(raw.get("outputs") or {}),
            signal=dict(raw.get("signal") or {}),
            thread=str(raw.get("thread", "")),
            resource=str(raw.get("resource", "")),
            chain=list(raw.get("chain") or []),
            index=int(raw.get("index", 0)),
            pending=[str(step_id) for step_id in raw.get("pending") or []],
            iterations=dict(raw.get("iterations") or {}),
            attempts=dict(raw.get("attempts") or {}),
            graph_id=str(raw.get("graph_id", "")),
            roster=dict(raw.get("roster") or {}),
            note=str(raw.get("note", "")),
            created_at=str(raw.get("created_at", "")),
            updated_at=str(raw.get("updated_at", "")),
        )


@dataclass
class Recall:
    """Thread memory as workers receive it."""

    working_memory: dict[str, Any] = field(default_factory=dict)
    observations: list[dict[str, Any]] = field(default_factory=list)
    summary: str = ""

    @property
    def texts(self) -> list[str]:
        return [str(item.get("text", "")) for item in self.observations]
