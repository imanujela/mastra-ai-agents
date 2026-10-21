"""The orchestrator state machine.

The engine owns every mutation of a ``Run``: it decides which steps are ready,
when a node has settled, and when a run is terminal. Workers never touch the
run; they return a result dict and the engine folds it in. Keeping all state
transitions here means a saved run can be restored and continued by any
process.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from .roster import parse_roster, resolve_step
from .types import ABORTED, BAILED, DONE, FAILED, RUNNING, Run, Step, utc_now


def _matches(when: dict[str, Any], signal: dict[str, Any]) -> bool:
    """A condition matches when every key/value it names is present in the signal."""
    return all(signal.get(key) == value for key, value in when.items())


def _raw_steps(node: dict[str, Any]) -> list[dict[str, Any]]:
    """Every step template a node owns, regardless of readiness rules."""
    op = node.get("op")
    if op == "then":
        return [node["step"]]
    if op == "branch":
        raws = [case["step"] for case in node.get("cases", [])]
        if node.get("default"):
            raws.append(node["default"])
        return raws
    return list(node.get("steps", []))


class Orchestrator:
    """Drives a graph by readying batches and folding in worker results."""

    def __init__(self, roster: dict[str, dict[str, Any]] | None = None) -> None:
        self.roster = parse_roster(roster)

    def start(
        self,
        graph: dict[str, Any],
        thread: str,
        resource: str,
        signal: dict[str, Any] | None = None,
    ) -> Run:
        """Create a run at the first node and ready its first batch."""
        stamp = utc_now()
        run = Run(
            id=uuid4().hex[:12],
            graph_id=str(graph["id"]),
            chain=list(graph["chain"]),
            thread=thread,
            resource=resource,
            signal=dict(signal or {}),
            created_at=stamp,
            updated_at=stamp,
        )
        self._ready_current(run)
        return run

    def complete(self, run: Run, step_id: str, result: dict[str, Any]) -> Run:
        """Fold one worker result into the run and move the state machine on."""
        if step_id not in run.pending:
            raise KeyError(step_id)
        step = self._find_step(run, step_id)
        run.outputs[step_id] = result
        if isinstance(result.get("signal"), dict):
            run.signal.update(result["signal"])
        attempts = run.attempts.get(step_id, 0) + 1
        run.attempts[step_id] = attempts

        if result.get("bail"):
            return self._finish(run, BAILED)
        if result.get("error"):
            retries = step.retries if step is not None else 0
            if attempts <= retries:
                run.status = RUNNING
                return self._touch(run)
            return self._finish(run, FAILED, note=str(result["error"]))

        run.pending.remove(step_id)
        run.ready = [ready for ready in run.ready if ready.id != step_id]
        if run.pending:
            run.status = RUNNING
            return self._touch(run)

        self._settle(run)
        return self._touch(run)

    def retry(self, run: Run, step_id: str) -> Run:
        """Put a settled step back in flight, discarding its old result."""
        step = self._find_step(run, step_id)
        if step is None:
            raise KeyError(step_id)
        if run.is_terminal:
            raise ValueError(f"run {run.id} is {run.status}; cannot retry")
        run.outputs.pop(step_id, None)
        run.attempts.pop(step_id, None)
        run.ready = [ready for ready in run.ready if ready.id != step_id] + [step]
        if step_id not in run.pending:
            run.pending.append(step_id)
        run.status = RUNNING
        return self._touch(run)

    def abort(self, run: Run, reason: str = "") -> Run:
        """Stop the run without pretending any work is still outstanding."""
        return self._finish(run, ABORTED, note=reason)

    def _find_step(self, run: Run, step_id: str) -> Step | None:
        """Recover a step definition from live work or from the graph itself."""
        for step in run.ready:
            if step.id == step_id:
                return step
        base, sep, suffix = step_id.rpartition("#")
        for node in run.chain:
            for raw in _raw_steps(node):
                raw_id = str(raw.get("id"))
                if sep and raw_id == base:
                    copy = self._copy_from_chain(run, node, raw, suffix)
                    if copy is not None:
                        return copy
                elif raw_id == step_id:
                    return resolve_step(raw, run, self.roster)
        return None

    def _copy_from_chain(
        self, run: Run, node: dict[str, Any], raw: dict[str, Any], suffix: str
    ) -> Step | None:
        """Rebuild a foreach or loop copy, whose id suffix identifies its origin."""
        if node.get("op") == "foreach" and suffix.isdigit():
            items = run.signal.get(str(node.get("over", "")))
            index = int(suffix)
            if isinstance(items, list) and 0 <= index < len(items):
                return self._foreach_step(run, node, raw, index, items[index])
        if node.get("op") == "loop" and suffix.startswith("r") and suffix[1:].isdigit():
            return self._loop_step(run, raw, int(suffix[1:]))
        return None

    def _ready_current(self, run: Run) -> None:
        """Ready the batch for the node at the cursor, skipping empty nodes."""
        if run.index >= len(run.chain):
            self._finish(run, DONE)
            return
        steps = self._node_steps(run, run.chain[run.index])
        if not steps:
            self._advance(run)
            return
        run.ready = steps
        run.pending = [step.id for step in steps]
        run.status = RUNNING

    def _node_steps(self, run: Run, node: dict[str, Any]) -> list[Step]:
        """Translate one graph node into the steps that are ready now."""
        op = node["op"]
        if op == "then":
            return [resolve_step(node["step"], run, self.roster)]
        if op == "parallel":
            return [resolve_step(step, run, self.roster) for step in node.get("steps", [])]
        if op == "branch":
            matched = [
                resolve_step(case["step"], run, self.roster)
                for case in node.get("cases", [])
                if _matches(case["when"], run.signal)
            ]
            if matched:
                return matched
            default = node.get("default")
            return [resolve_step(default, run, self.roster)] if default else []
        if op == "foreach":
            return self._foreach_steps(run, node)
        if op == "loop":
            return self._loop_steps(run, node)
        raise ValueError(f"unknown op: {op!r}")

    def _foreach_steps(self, run: Run, node: dict[str, Any]) -> list[Step]:
        """Fan one block out over the signal list, item-major and index-addressed."""
        over = str(node.get("over", ""))
        items = run.signal.get(over)
        if not isinstance(items, list):
            raise ValueError(f"foreach over {over!r} requires a list in the signal")
        return [
            self._foreach_step(run, node, raw, index, item)
            for index, item in enumerate(items)
            for raw in node.get("steps", [])
        ]

    def _foreach_step(
        self,
        run: Run,
        node: dict[str, Any],
        raw: dict[str, Any],
        index: int,
        item: Any,
    ) -> Step:
        """Copy one block step for one item, keeping its meta and adding item facts."""
        meta = dict(raw.get("meta") or {})
        meta["item"] = item
        meta["index"] = index
        if "max_parallel" in node:
            meta["max_parallel"] = node["max_parallel"]
        copy = dict(raw)
        copy["id"] = f"{raw['id']}#{index}"
        copy["instruction"] = str(raw.get("instruction", "")).replace("{{item}}", str(item))
        copy["meta"] = meta
        return resolve_step(copy, run, self.roster)

    def _loop_steps(self, run: Run, node: dict[str, Any]) -> list[Step]:
        """Emit the next numbered pass of a loop block, unless the cap is spent."""
        key = str(run.index)
        iteration = run.iterations.get(key, 0) + 1
        if iteration > int(node.get("max_iterations", 1)):
            return []
        run.iterations[key] = iteration
        return [self._loop_step(run, raw, iteration) for raw in node.get("steps", [])]

    def _loop_step(self, run: Run, raw: dict[str, Any], iteration: int) -> Step:
        copy = dict(raw)
        copy["id"] = f"{raw['id']}#r{iteration}"
        return resolve_step(copy, run, self.roster)

    def _settle(self, run: Run) -> None:
        """Decide what follows a fully settled node: another loop pass or the next node."""
        node = run.chain[run.index]
        if node.get("op") == "loop" and not self._loop_is_done(run, node):
            self._ready_current(run)
            return
        self._advance(run)

    def _loop_is_done(self, run: Run, node: dict[str, Any]) -> bool:
        """A loop ends when its until-clause matches or the iteration cap is reached."""
        if _matches(node.get("until") or {}, run.signal):
            return True
        return run.iterations.get(str(run.index), 0) >= int(node.get("max_iterations", 1))

    def _advance(self, run: Run) -> None:
        """Move past the settled node, finishing the run at the chain end."""
        run.index += 1
        run.ready = []
        run.pending = []
        self._ready_current(run)

    def _finish(self, run: Run, status: str, note: str = "") -> Run:
        """Put the run in a terminal state with no outstanding work."""
        run.status = status
        run.ready = []
        run.pending = []
        run.note = note
        return self._touch(run)

    @staticmethod
    def _touch(run: Run) -> Run:
        run.updated_at = utc_now()
        return run
