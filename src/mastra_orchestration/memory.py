"""Thread memory: working memory merge and observational notes."""

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Recall:
    working_memory: dict
    observations: list[str] = field(default_factory=list)


class Memory:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def remember(self, thread, resource, working_memory=None, observation=None):
        path = self._path(thread, resource)
        data = {"working_memory": {}, "observations": []}
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
        if working_memory:
            data["working_memory"].update(working_memory)
        if observation:
            data["observations"].append(observation)
        path.write_text(json.dumps(data), encoding="utf-8")

    def recall(self, thread, resource):
        path = self._path(thread, resource)
        if not path.exists():
            return Recall({}, [])
        data = json.loads(path.read_text(encoding="utf-8"))
        return Recall(data.get("working_memory", {}), list(data.get("observations", [])))

    def _path(self, thread, resource):
        safe = f"{resource}__{thread}".replace("/", "_").replace("\\", "_")
        return self.root / f"{safe}.json"
