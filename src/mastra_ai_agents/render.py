"""Structural views of a graph: Mermaid for docs, ASCII for terminals.

Both views are read-only and deterministic, so rendered diagrams can be
committed next to a graph and diffed like any other file.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from .types import FAILED, Run

INSTRUCTION_LIMIT = 60

RUN_CLASS_DEFS = (
    "  classDef done fill:#1b5e20,color:#ffffff",
    "  classDef active fill:#0d47a1,color:#ffffff",
    "  classDef pending fill:#37474f,color:#ffffff",
    "  classDef failed fill:#b71c1c,color:#ffffff",
)


def _flatten(text: Any) -> str:
    """Collapse any whitespace, including newlines, so a value stays on one line."""
    return " ".join(str(text).split())


def _scalar(value: Any) -> str:
    """Render a signal value the way JSON spells it, not the way Python does."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    return _flatten(value)


def _escape(text: Any) -> str:
    """Escape characters Mermaid would otherwise read as markup.

    A quote ends a label, an entity code starts with `#`, and angle brackets
    are parsed as HTML. Only a `#` that already looks like an entity is
    escaped, so step ids such as `extract#i` stay readable.
    """
    flat = _flatten(text)
    flat = re.sub(r"#(?=[A-Za-z0-9]+;)", "#35;", flat)
    return (
        flat.replace('"', "#quot;")
        .replace("<", "#lt;")
        .replace(">", "#gt;")
        .replace("|", "#124;")
    )


def _instruction(raw: dict[str, Any]) -> str:
    return _flatten(raw.get("instruction", ""))[:INSTRUCTION_LIMIT]


def _label(raw: dict[str, Any], display_id: str | None = None) -> str:
    return f"{_escape(display_id or raw['id'])} · {_escape(raw['agent'])} — {_escape(_instruction(raw))}"


def _when_text(when: dict[str, Any]) -> str:
    """A when-clause reads as `key=value` pairs joined when all must match.

    Kept unescaped so the ASCII tree stays literal; callers that embed it in
    Mermaid escape it at the edge and subgraph boundary.
    """
    return " & ".join(f"{key}={_scalar(value)}" for key, value in when.items())


class _Ids:
    """Allocate Mermaid-safe ids, suffixing collisions so every identifier is unique."""

    def __init__(self) -> None:
        self._used: set[str] = set()

    def take(self, raw: Any, prefix: str = "") -> str:
        base = prefix + re.sub(r"[^A-Za-z0-9_]", "_", str(raw))
        if not base or base[0].isdigit():
            base = "n_" + base
        candidate, suffix = base, 2
        while candidate in self._used:
            candidate = f"{base}_{suffix}"
            suffix += 1
        self._used.add(candidate)
        return candidate


class _Mermaid:
    """Walk a chain once, emitting nodes in order and edges between them.

    `tails` is the frontier the next op waits for: parallel and branch widen
    it, then and the block ops narrow it back to one successor.
    """

    def __init__(
        self,
        chain: list[dict[str, Any]],
        class_for: Callable[[str], str] | None = None,
    ) -> None:
        self.lines: list[str] = ["flowchart TD"]
        self.ids = _Ids()
        self.chain = chain
        self.class_for = class_for
        self.nodes: list[tuple[str, str]] = []
        self.tails: list[str] = []
        self.depth = 0
        self.loops = 0

    def emit(self, text: str) -> None:
        self.lines.append("  " * (self.depth + 1) + text)

    def node(self, raw: dict[str, Any], alias: str | None = None) -> str:
        node_id = self.ids.take(alias or raw["id"])
        self.nodes.append((node_id, raw["id"]))
        css = f":::{self.class_for(raw['id'])}" if self.class_for else ""
        self.emit(f'{node_id}["{_label(raw, alias)}"]{css}')
        return node_id

    def connect(self, sources: list[str], targets: list[str], label: str | None = None) -> None:
        arrow = f"-->|{_escape(label)}|" if label else "-->"
        for source in sources:
            for target in targets:
                self.emit(f"{source} {arrow} {target}")

    def open_subgraph(self, raw_id: str, title: str, prefix: str = "sub_") -> str:
        sub_id = self.ids.take(raw_id, prefix=prefix)
        self.emit(f'subgraph {sub_id}["{_escape(title)}"]')
        self.depth += 1
        self.emit("direction TB")
        return sub_id

    def close_subgraph(self) -> None:
        self.depth -= 1
        self.emit("end")

    def render(self) -> str:
        for node in self.chain:
            self.visit(node)
        return "\n".join(self.lines)

    def visit(self, node: dict[str, Any]) -> None:
        op = node.get("op")
        if op == "then":
            self.tails = self.then(node)
        elif op == "parallel":
            self.tails = self.parallel(node)
        elif op == "branch":
            self.tails = self.branch(node)
        elif op == "foreach":
            self.tails = self.foreach(node)
        elif op == "loop":
            self.tails = self.loop(node)

    def then(self, node: dict[str, Any]) -> list[str]:
        step = self.node(node["step"])
        self.connect(self.tails, [step])
        return [step]

    def parallel(self, node: dict[str, Any]) -> list[str]:
        steps = [self.node(raw) for raw in node["steps"]]
        self.connect(self.tails, steps)
        return steps or list(self.tails)

    def branch(self, node: dict[str, Any]) -> list[str]:
        targets: list[str] = []
        for case in node.get("cases") or []:
            step = self.node(case["step"])
            self.connect(self.tails, [step], label=f"when {_when_text(case.get('when') or {})}")
            targets.append(step)
        if node.get("default"):
            step = self.node(node["default"])
            self.connect(self.tails, [step], label="default")
            targets.append(step)
        return targets or list(self.tails)

    def foreach(self, node: dict[str, Any]) -> list[str]:
        over = str(node.get("over", "items"))
        steps = node["steps"]
        sub_id = self.open_subgraph(over, f"foreach over {over}", prefix="sub_foreach_")
        head: str | None = None
        for raw in steps:
            step = self.node(raw, alias=f"{raw['id']}#i")
            if head:
                self.connect([head], [step])
            head = step
        self.close_subgraph()
        self.emit(self.foreach_note(over, len(steps)))
        self.connect(self.tails, [sub_id])
        return [sub_id]

    @staticmethod
    def foreach_note(over: str, count: int) -> str:
        """The representative chain stands in for every item, so note the edges it hides."""
        edges = max(count - 1, 0)
        plural = "edge" if edges == 1 else "edges"
        return f"%% foreach over {over}: {count} steps per item, 1 representative chain, {edges} internal {plural}"

    def loop(self, node: dict[str, Any]) -> list[str]:
        self.loops += 1
        until = _when_text(node.get("until") or {})
        sub_id = self.open_subgraph(f"loop_{self.loops}", f"loop until {until} max {node['max_iterations']}")
        head: str | None = None
        for raw in node["steps"]:
            step = self.node(raw)
            if head:
                self.connect([head], [step])
            head = step
        self.close_subgraph()
        self.connect(self.tails, [sub_id])
        return [sub_id]


def to_mermaid(graph: dict[str, Any]) -> str:
    """Render a graph definition as a Mermaid flowchart for docs and review."""
    return _Mermaid(list(graph.get("chain") or [])).render()


def _matches(keys: Any, step_id: str) -> bool:
    """A foreach step is stored per item as `<id>#<i>`, so variants count as the step."""
    return any(str(key) == step_id or str(key).startswith(f"{step_id}#") for key in keys)


def run_mermaid(run: Run) -> str:
    """Render a saved run: the graph's shape plus each step's live status.

    The title line carries progress, and inline classes let one diagram show
    what finished, what is ready, and what a failure blocked.
    """

    def class_for(step_id: str) -> str:
        if _matches(run.outputs, step_id):
            return "done"
        if _matches(run.ready_ids(), step_id):
            return "active"
        return "failed" if run.status == FAILED else "pending"

    view = _Mermaid(list(run.chain or []), class_for=class_for)
    lines = view.render().splitlines()
    completed = sum(1 for _, step_id in view.nodes if class_for(step_id) == "done")
    lines.insert(1, f"%% run {_flatten(run.id)} {run.status} {completed}/{len(view.nodes)}")
    lines.extend(RUN_CLASS_DEFS)
    return "\n".join(lines)


def _ascii_step(raw: dict[str, Any], depth: int) -> str:
    return "  " * depth + f"{raw['id']} ({raw['agent']})"


def to_ascii(graph: dict[str, Any]) -> str:
    """Render the chain as a plain-text tree.

    Windows consoles and log files get no box-drawing glyphs: indentation and
    counts alone carry the structure, so the output pastes anywhere.
    """
    lines: list[str] = []
    for node in graph.get("chain") or []:
        op = node.get("op")
        if op == "then":
            lines.append(f"then  {node['step']['id']} ({node['step']['agent']})")
        elif op == "parallel":
            steps = node["steps"]
            lines.append(f"parallel ({len(steps)} steps)")
            lines.extend(_ascii_step(raw, 1) for raw in steps)
        elif op == "branch":
            cases = node.get("cases") or []
            lines.append(f"branch {len(cases)} cases")
            for case in cases:
                lines.append(f"  when {_when_text(case.get('when') or {})}")
                lines.append(_ascii_step(case["step"], 2))
            if node.get("default"):
                lines.append("  default")
                lines.append(_ascii_step(node["default"], 2))
        elif op == "foreach":
            over = str(node.get("over", "items"))
            steps = node["steps"]
            lines.append(f"foreach over {over} ({len(steps)} steps each)")
            lines.extend(_ascii_step(raw, 1) for raw in steps)
        elif op == "loop":
            steps = node["steps"]
            until = _when_text(node.get("until") or {})
            lines.append(f"loop until {until} max {node['max_iterations']} ({len(steps)} steps)")
            lines.extend(_ascii_step(raw, 1) for raw in steps)
    return "\n".join(lines)
