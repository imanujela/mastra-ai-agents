"""What one run teaches the next.

Every finished run feeds a smoothed success rate per planning template. The next plan reads that
rate, so a template that keeps ending in ``failed`` or ``bailed`` stops being chosen without anyone
editing code. Add-one smoothing keeps a single lucky run from dominating.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from mastra_ai_agents.types import utc_now

OUTCOMES = frozenset({"done", "bailed", "failed", "aborted"})


class Policy:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def observe(self, template: str, outcome: str, weight: float = 1.0) -> dict[str, Any]:
        if outcome not in OUTCOMES:
            raise ValueError(f"outcome must be one of {sorted(OUTCOMES)}, got {outcome!r}")
        if weight <= 0:
            raise ValueError("weight must be positive")
        data = self._load()
        cell = data["templates"].setdefault(template, {"attempts": 0, "successes": 0})
        cell["attempts"] += 1
        if outcome == "done":
            cell["successes"] += 1
        data["updated_at"] = utc_now()
        self._save(data)
        return {
            "attempts": cell["attempts"],
            "successes": cell["successes"],
            "rate": round(self._rate(cell), 4),
        }

    def rank(self, templates: list[str]) -> list[str]:
        data = self._load()["templates"]
        return sorted(
            templates,
            key=lambda name: (
                -self._rate(data.get(name)),
                -data.get(name, {}).get("attempts", 0),
                templates.index(name),
            ),
        )

    def snapshot(self) -> dict[str, Any]:
        data = self._load()
        return {"templates": {name: dict(cell) for name, cell in data["templates"].items()},
                "updated_at": data.get("updated_at", "")}

    def to_context(self, limit: int = 3) -> str:
        templates = self._load()["templates"]
        if not templates:
            return "Policy: no prior runs."
        ranked = self.rank(list(templates))[:limit]
        parts = []
        for name in ranked:
            cell = templates[name]
            parts.append(f"{name} {self._rate(cell):.0%} over {cell['attempts']}")
        return "Policy (smoothed success): " + ", ".join(parts)

    @staticmethod
    def _rate(cell: dict | None) -> float:
        if not cell:
            return 0.5
        return (cell.get("successes", 0) + 1) / (cell.get("attempts", 0) + 2)

    def _load(self) -> dict:
        if not self.path.exists():
            return {"templates": {}, "updated_at": ""}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"templates": {}, "updated_at": ""}
        if not isinstance(data, dict) or not isinstance(data.get("templates"), dict):
            return {"templates": {}, "updated_at": ""}
        return data

    def _save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)
