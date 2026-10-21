"""Durable run storage.

One JSON file per run lives under ``<root>/runs``; ``index.json`` is a small
summary so listing a directory of runs never has to parse whole runs. The run
files are the source of truth, so a missing or torn index can be rebuilt from
them instead of taking the runs down with it.

Every write goes to a sibling ``.tmp`` file, is flushed and fsynced, and is
then swapped in with :func:`os.replace` -- on Windows that is the atomic
``MoveFileEx(REPLACE_EXISTING)`` path, so a crash leaves either the old file or
the new one, never half of either.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .types import Run


class RunStore:
    """Filesystem-backed store for :class:`Run` objects."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.runs_dir = self.root / "runs"
        self.index_path = self.runs_dir / "index.json"

    def save(self, run: Run) -> Path:
        """Persist ``run`` atomically and refresh its index entry.

        The caller owns ``run.updated_at``; the store only records it.
        """
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        path = self._run_path(run.id)
        _atomic_write_json(path, run.to_dict())
        entries = self._entries()
        entries[run.id] = _entry_for(run)
        self._write_index(entries)
        return path

    def load(self, run_id: str) -> Run:
        """Read one run back; a missing run is an error worth naming."""
        path = self._run_path(run_id)
        if not path.is_file():
            raise FileNotFoundError(f"run not found: {path}")
        return Run.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def exists(self, run_id: str) -> bool:
        return self._run_path(run_id).is_file()

    def delete(self, run_id: str) -> bool:
        """Drop the run, its event log and its index entry; True if anything went."""
        removed = False
        path = self._run_path(run_id)
        if path.is_file():
            path.unlink()
            removed = True
        events = self.runs_dir / f"{run_id}.events.jsonl"
        if events.is_file():
            events.unlink()
            removed = True
        entries = self._entries()
        if run_id in entries:
            del entries[run_id]
            self._write_index(entries)
            removed = True
        return removed

    def list(self, status: str | None = None, limit: int | None = None) -> list[dict[str, Any]]:
        """Index entries, newest-updated first, optionally filtered and capped."""
        entries = list(self._entries().values())
        if status is not None:
            entries = [entry for entry in entries if entry.get("status") == status]
        entries.sort(key=lambda entry: entry.get("updated_at", ""), reverse=True)
        if limit is not None:
            entries = entries[:limit]
        return entries

    def latest(self, thread: str | None = None) -> dict[str, Any] | None:
        """Newest index entry, for resuming the most recent run of a thread."""
        entries = self.list()
        if thread is not None:
            entries = [entry for entry in entries if entry.get("thread") == thread]
        return entries[0] if entries else None

    def _run_path(self, run_id: str) -> Path:
        return self.runs_dir / f"{run_id}.json"

    def _entries(self) -> dict[str, dict[str, Any]]:
        """The index, rebuilt from run files when it is missing or unreadable."""
        entries = self._read_index()
        if entries is not None:
            return entries
        if not self.runs_dir.is_dir():
            return {}
        entries = self._rebuild_index()
        self._write_index(entries)
        return entries

    def _read_index(self) -> dict[str, dict[str, Any]] | None:
        try:
            raw = json.loads(self.index_path.read_text(encoding="utf-8"))
            entries = raw["runs"]
            if not isinstance(entries, dict):
                return None
            return {str(key): dict(value) for key, value in entries.items()}
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def _rebuild_index(self) -> dict[str, dict[str, Any]]:
        """Recover the index from the run files, skipping any unreadable run."""
        entries: dict[str, dict[str, Any]] = {}
        for path in sorted(self.runs_dir.glob("*.json")):
            if path == self.index_path:
                continue
            try:
                run = Run.from_dict(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError, KeyError, TypeError):
                continue
            entries[run.id] = _entry_for(run)
        return entries

    def _write_index(self, entries: dict[str, dict[str, Any]]) -> None:
        _atomic_write_json(self.index_path, {"runs": entries})


def _entry_for(run: Run) -> dict[str, Any]:
    """The list-view summary of a run: enough to pick the next one, no payload."""
    return {
        "id": run.id,
        "graph_id": run.graph_id,
        "status": run.status,
        "thread": run.thread,
        "resource": run.resource,
        "ready": len(run.ready),
        "created_at": run.created_at,
        "updated_at": run.updated_at,
    }


def _atomic_write_json(path: Path, payload: Any) -> None:
    """Write ``payload`` through a same-directory tmp file plus ``os.replace``."""
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)
