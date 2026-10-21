"""Thread memory: merged working memory plus observational notes.

Each ``(resource, thread)`` pair owns one JSON file at ``<root>/<resource>__<thread>.json``
(slashes flattened, because both names may come from user input). Writes use
the same same-directory tmp-plus-``os.replace`` path as the run store, so a
worker never recalls a half-written memory.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .types import Recall, utc_now

MAX_OBSERVATIONS = 200


class Memory:
    """Per-thread memory that survives across runs of the same conversation."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def remember(
        self,
        thread: str,
        resource: str,
        working_memory: dict[str, Any] | None = None,
        observation: str | None = None,
        summary: str | None = None,
    ) -> Recall:
        """Merge new facts, append a note and persist atomically."""
        path = self._path(thread, resource)
        data = self._read(path)
        working = data.get("working_memory")
        working = dict(working) if isinstance(working, dict) else {}
        if working_memory is not None:
            working.update(working_memory)
        observations = _observations(data.get("observations"))
        if isinstance(observation, str) and observation:
            observations.append({"ts": utc_now(), "text": observation})
        # Compaction: a long-running thread keeps its newest 200 notes, not every note.
        observations = observations[-MAX_OBSERVATIONS:]
        summary_text = str(data.get("summary", ""))
        if summary is not None:
            summary_text = str(summary)
        payload = {
            "thread": thread,
            "resource": resource,
            "working_memory": working,
            "observations": observations,
            "summary": summary_text,
            "updated_at": utc_now(),
        }
        _atomic_write_json(path, payload)
        return Recall(
            working_memory=dict(working),
            observations=[dict(item) for item in observations],
            summary=payload["summary"],
        )

    def recall(self, thread: str, resource: str) -> Recall:
        """Everything remembered for this thread; empty when nothing is stored."""
        path = self._path(thread, resource)
        if not path.is_file():
            return Recall()
        data = self._read(path)
        working = data.get("working_memory")
        return Recall(
            working_memory=dict(working) if isinstance(working, dict) else {},
            observations=_observations(data.get("observations")),
            summary=str(data.get("summary", "")),
        )

    def forget(self, thread: str, resource: str) -> bool:
        """Delete one thread's memory; False when there was nothing to delete."""
        path = self._path(thread, resource)
        if path.is_file():
            path.unlink()
            return True
        return False

    def threads(self, resource: str | None = None) -> list[dict[str, Any]]:
        """Summarise stored threads, newest first, for a memory listing.

        Identity comes from the file name (that is the only place it is
        guaranteed to exist), so the values are the flattened ones. Corrupt
        files are skipped: one bad file must not hide the rest.
        """
        wanted = _flatten(resource) if resource is not None else None
        found: list[tuple[tuple[str, int], dict[str, Any]]] = []
        for path in self.root.glob("*.json"):
            name = path.stem
            if "__" not in name:
                continue
            resource_name, thread_name = name.split("__", 1)
            if wanted is not None and resource_name != wanted:
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                mtime = path.stat().st_mtime_ns
            except (OSError, ValueError):
                continue
            if not isinstance(data, dict):
                continue
            observations = data.get("observations")
            updated = data.get("updated_at")
            if not isinstance(updated, str) or not updated:
                updated = datetime.fromtimestamp(mtime / 1_000_000_000, UTC).isoformat(
                    timespec="seconds"
                )
            # Second-precision timestamps tie easily; mtime keeps newest-first honest.
            found.append(
                (
                    (updated, mtime),
                    {
                        "thread": thread_name,
                        "resource": resource_name,
                        "observations": len(observations) if isinstance(observations, list) else 0,
                        "updated_at": updated,
                    },
                )
            )
        found.sort(key=lambda item: item[0], reverse=True)
        return [entry for _, entry in found]

    def _path(self, thread: str, resource: str) -> Path:
        name = _flatten(f"{resource}__{thread}")
        return self.root / f"{name}.json"

    @staticmethod
    def _read(path: Path) -> dict[str, Any]:
        if not path.is_file():
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}


def _flatten(name: str) -> str:
    """Make a resource or thread name safe as one file-name segment."""
    return name.replace("/", "_").replace("\\", "_")


def _observations(raw: Any) -> list[dict[str, Any]]:
    """Normalise notes, coercing the v0.1 plain-string form; drop the rest."""
    if not isinstance(raw, list):
        return []
    observations: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, str):
            observations.append({"ts": "", "text": item})
        elif isinstance(item, dict):
            observations.append(dict(item))
    return observations


def _atomic_write_json(path: Path, payload: Any) -> None:
    """Write through a same-directory tmp file, then swap with ``os.replace``."""
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)
