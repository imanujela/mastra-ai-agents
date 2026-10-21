from mastra_orchestration.memory import Memory

__all__ = ["Memory", "Orchestrator", "Run", "Step"]

from dataclasses import dataclass, field


@dataclass
class Step:
    id: str
    agent: str
    instruction: str
    memory_thread: str | None = None
    resource: str | None = None


@dataclass
class Run:
    ready: list[Step]
    status: str
    outputs: dict = field(default_factory=dict)
    signal: dict = field(default_factory=dict)
    thread: str = ""
    resource: str = ""
    _chain: list[dict] = field(default_factory=list)
    _index: int = 0
    _pending: set[str] = field(default_factory=set)


def _matches(when: dict, signal: dict) -> bool:
    return all(signal.get(key) == value for key, value in when.items())


def _as_step(raw: dict, run: Run, roster: dict) -> Step:
    own_memory = bool(roster.get(raw["agent"], {}).get("own_memory", False))
    return Step(
        raw["id"],
        raw["agent"],
        raw["instruction"],
        memory_thread=None if own_memory else run.thread,
        resource=None if own_memory else run.resource,
    )


class Orchestrator:
    def __init__(self, roster=None):
        self.roster = roster or {}

    def start(self, graph, thread, resource, signal=None):
        run = Run(
            ready=[],
            status="running",
            _chain=graph["chain"],
            signal=dict(signal or {}),
            thread=thread,
            resource=resource,
        )
        self._ready_current(run)
        return run

    def complete(self, run, step_id, result):
        if step_id not in run._pending:
            raise KeyError(step_id)
        run.outputs[step_id] = result
        if isinstance(result, dict) and isinstance(result.get("signal"), dict):
            run.signal.update(result["signal"])
        run._pending.remove(step_id)
        run.ready = [step for step in run.ready if step.id != step_id]
        if isinstance(result, dict) and result.get("bail"):
            run.ready = []
            run._pending = set()
            run.status = "bailed"
            return run
        if run._pending:
            return run
        run._index += 1
        if run._index >= len(run._chain):
            run.ready = []
            run.status = "done"
            return run
        self._ready_current(run)
        return run

    def _ready_current(self, run):
        node = run._chain[run._index]
        if node["op"] == "then":
            steps = [_as_step(node["step"], run, self.roster)]
        elif node["op"] == "parallel":
            steps = [_as_step(raw, run, self.roster) for raw in node["steps"]]
        elif node["op"] == "branch":
            steps = [
                _as_step(case["step"], run, self.roster)
                for case in node["cases"]
                if _matches(case["when"], run.signal)
            ]
        else:
            raise ValueError(node["op"])
        if not steps:
            run._index += 1
            if run._index >= len(run._chain):
                run.ready = []
                run._pending = set()
                run.status = "done"
                return
            self._ready_current(run)
            return
        run.ready = steps
        run._pending = {step.id for step in steps}
        run.status = "running"

