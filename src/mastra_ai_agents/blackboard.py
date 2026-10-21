"""Stigmergic run memory.

Workers post findings and risks as they finish; the next worker's context carries the digest of
what the swarm already knows. A later reader needs no direct link to the writer, which is what
makes a wide fan-out legible instead of a pile of isolated answers.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from mastra_ai_agents.types import utc_now

BODY_LIMIT = 2000


class Blackboard:
    """One JSON file per run under ``<root>/blackboard``."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.dir = self.root / "blackboard"
        self.dir.mkdir(parents=True, exist_ok=True)

    def post(
        self,
        run_id: str,
        step_id: str,
        kind: str,
        title: str,
        body: str = "",
        tags: Iterable[str] = (),
        score: float | None = None,
    ) -> dict[str, Any]:
        if not str(title).strip():
            raise ValueError("a blackboard entry needs a title")
        data = self._read(run_id)
        data["seq"] += 1
        entry = {
            "id": f"e{data['seq']}",
            "seq": data["seq"],
            "run_id": run_id,
            "step_id": step_id,
            "kind": kind,
            "title": str(title).strip(),
            "body": str(body)[:BODY_LIMIT],
            "tags": list(tags),
            "score": score,
            "ts": utc_now(),
        }
        data["entries"].append(entry)
        self._write(run_id, data)
        return entry

    def entries(self, run_id: str, tag: str | None = None, kind: str | None = None) -> list[dict]:
        items = self._read(run_id)["entries"]
        if tag is not None:
            items = [entry for entry in items if tag in entry["tags"]]
        if kind is not None:
            items = [entry for entry in items if entry["kind"] == kind]
        return items

    def digest(self, run_id: str, limit: int = 12) -> str:
        """A context block short enough to hand every worker on the next wave."""
        items = self.entries(run_id)[-limit:]
        if not items:
            return ""
        lines = ["Blackboard (newest last):"]
        for entry in items:
            body = " ".join(entry["body"].split())[:160]
            suffix = f": {body}" if body else ""
            lines.append(f"- [{entry['kind']}] {entry['title']} ({entry['step_id']}){suffix}")
        return "\n".join(lines)

    def prune(self, run_id: str, keep: int = 500) -> int:
        data = self._read(run_id)
        entries = data["entries"]
        if len(entries) <= keep:
            return 0
        data["entries"] = entries[-keep:]
        self._write(run_id, data)
        return len(entries) - keep

    def _path(self, run_id: str) -> Path:
        return self.dir / f"{run_id}.json"

    def _read(self, run_id: str) -> dict:
        path = self._path(run_id)
        if not path.exists():
            return {"run_id": run_id, "seq": 0, "entries": []}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"blackboard for {run_id} is not valid JSON: {path}") from exc
        data.setdefault("seq", len(data.get("entries", [])))
        data.setdefault("entries", [])
        return data

    def _write(self, run_id: str, data: dict) -> None:
        path = self._path(run_id)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)
