"""Append-only event log for runs.

Each run gets ``<runs_dir>/<run_id>.events.jsonl`` -- one JSON object per line.
Appending is a single open-write-flush-fsync per event, never a rewrite, so a
crash can only ever tear the final line; readers skip unparseable lines rather
than let a torn tail hide the history before it.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .types import utc_now


class EventLog:
    """JSONL history beside the run files it describes."""

    def __init__(self, runs_dir: str | Path):
        self.runs_dir = Path(runs_dir)

    def append(self, run_id: str, event: str, **fields: Any) -> dict[str, Any]:
        """Record one event and return exactly what was written."""
        record = {"ts": utc_now(), "run_id": run_id, "event": event, **fields}
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        path = self._path(run_id)
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        return record

    def read(self, run_id: str) -> list[dict[str, Any]]:
        """Every parseable event for ``run_id``, oldest first."""
        path = self._path(run_id)
        if not path.is_file():
            return []
        events: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if isinstance(event, dict):
                    events.append(event)
        return events

    def tail(self, run_id: str, n: int = 20) -> list[dict[str, Any]]:
        """The newest ``n`` events, for showing recent progress cheaply."""
        if n <= 0:
            return []
        return self.read(run_id)[-n:]

    def _path(self, run_id: str) -> Path:
        return self.runs_dir / f"{run_id}.events.jsonl"
