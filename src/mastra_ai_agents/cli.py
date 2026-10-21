"""The only module that prints.

One JSON object per call on stdout, and an exit code that means something: 0 done, 2 invalid
(usage, graph, or result), 3 missing (run, step, thread), 4 the run's status forbids the
transition. Library modules return data and raise; every error becomes JSON at this edge.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .engine import Orchestrator
from .events import EventLog
from .graph import parse_graph
from .memory import Memory
from .render import run_mermaid, to_ascii, to_mermaid
from .roster import parse_roster
from .store import RunStore
from .swarm import Swarm, build_graph, choose_template, templates
from .types import Run
from .validate import GraphError, validate_graph

OK = 0
INVALID = 2
MISSING = 3
CONFLICT = 4


class Conflict(Exception):
    """A transition the run's status forbids, e.g. retrying a finished run."""


def default_root() -> Path:
    if os.environ.get("MASTRA_ROOT"):
        return Path(os.environ["MASTRA_ROOT"]).expanduser()
    if os.environ.get("HERMES_HOME"):
        return Path(os.environ["HERMES_HOME"]).expanduser() / "mastra-orchestration"
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "hermes" / "mastra-orchestration"
    return Path.home() / ".local" / "share" / "hermes" / "mastra-orchestration"


def _value(text: str) -> Any:
    """Accept inline JSON or a path to a JSON file; both are common in a shell."""
    candidate = Path(text)
    if candidate.is_file():
        return json.loads(candidate.read_text(encoding="utf-8"))
    return json.loads(text)


def _graph(path: str) -> dict[str, Any]:
    return parse_graph(json.loads(Path(path).read_text(encoding="utf-8")))


def _emit(payload: Any, pretty: bool) -> None:
    print(json.dumps(payload, indent=2 if pretty else None, ensure_ascii=False))


def _fail(message: str, code: int, **extra: Any) -> int:
    _emit({"error": message, **extra}, False)
    return code


def _engine(run: Run) -> Orchestrator:
    return Orchestrator(roster=run.roster)


def _save(store: RunStore, events: EventLog, run: Run, event: str, **fields: Any) -> dict:
    store.save(run)
    events.append(run.id, event, status=run.status, **fields)
    return run.to_dict()


def _mutate(args: argparse.Namespace, root: Path, action: str) -> tuple[dict, int]:
    store, events = RunStore(root), EventLog(root / "runs")
    run = store.load(args.run)
    if run.is_terminal:
        raise Conflict(f"run {run.id} is {run.status}")
    engine = _engine(run)
    if action == "retry":
        engine.retry(run, args.step)
    elif action == "abort":
        engine.abort(run, args.reason)
    return _save(store, events, run, action, step=getattr(args, "step", "")), OK


def _dispatch(args: argparse.Namespace, root: Path) -> tuple[dict, int]:
    command = args.command
    store = RunStore(root)

    if command == "start":
        roster = parse_roster(_value(args.roster) if args.roster else None)
        graph = _graph(args.graph)
        run = Orchestrator(roster=roster).start(
            graph,
            thread=args.thread,
            resource=args.resource,
            signal=_value(args.signal) if args.signal else None,
        )
        run.roster = roster
        if args.id:
            run.id = args.id
        return _save(store, EventLog(root / "runs"), run, "started", graph=graph["id"]), OK

    if command == "complete":
        run = store.load(args.run)
        if run.is_terminal:
            raise Conflict(f"run {run.id} is {run.status}")
        result = _value(args.result)
        if ":" in run.graph_id:
            # A swarm run must reach the blackboard and the policy, whichever verb records it.
            Swarm(root, roster=run.roster).record(run, args.step, result)
            return run.to_dict(), OK
        Orchestrator(roster=run.roster).complete(run, args.step, result)
        return _save(store, EventLog(root / "runs"), run, "completed", step=args.step), OK

    if command in {"retry", "abort"}:
        return _mutate(args, root, command)

    if command == "show":
        return store.load(args.run).to_dict(), OK

    if command == "status":
        run = store.load(args.run)
        return (
            {
                "run_id": run.id,
                "graph_id": run.graph_id,
                "status": run.status,
                "index": run.index,
                "chain_length": len(run.chain),
                "ready": run.ready_ids(),
                "pending": list(run.pending),
                "outputs": len(run.outputs),
                "attempts": dict(run.attempts),
                "note": run.note,
                "updated_at": run.updated_at,
            },
            OK,
        )

    if command == "list":
        return {"runs": store.list(status=args.status, limit=args.limit)}, OK

    if command == "resume":
        return store.load(args.run).to_dict(), OK

    if command == "recall":
        recalled = Memory(root / "memory").recall(args.thread, args.resource)
        return {
            "working_memory": recalled.working_memory,
            "observations": recalled.observations,
            "summary": recalled.summary,
        }, OK

    if command == "remember":
        recalled = Memory(root / "memory").remember(
            args.thread,
            args.resource,
            working_memory=_value(args.working_memory) if args.working_memory else None,
            observation=args.observation or None,
            summary=args.summary or None,
        )
        return {
            "working_memory": recalled.working_memory,
            "observations": recalled.observations,
            "summary": recalled.summary,
        }, OK

    if command == "validate":
        raw = json.loads(Path(args.graph).read_text(encoding="utf-8"))
        problems = validate_graph(raw)
        return {"valid": not problems, "problems": problems}, (OK if not problems else INVALID)

    if command == "render":
        if args.run:
            return {"format": "mermaid", "text": run_mermaid(store.load(args.run))}, OK
        graph = _graph(args.graph)
        if args.format == "ascii":
            return {"format": "ascii", "text": to_ascii(graph)}, OK
        return {"format": "mermaid", "text": to_mermaid(graph)}, OK

    if command == "events":
        log = EventLog(root / "runs")
        events = log.tail(args.run, args.tail) if args.tail else log.read(args.run)
        return {"events": events}, OK

    if command == "export":
        run = store.load(args.run)
        if args.out:
            Path(args.out).write_text(json.dumps(run.to_dict(), indent=2), encoding="utf-8")
            return {"exported": str(Path(args.out).resolve())}, OK
        return run.to_dict(), OK

    if command == "doctor":
        return _doctor(root), OK

    if command == "swarm":
        return _swarm(args, root)

    raise ValueError(f"unknown command: {command}")


def _doctor(root: Path) -> dict:
    try:
        root.mkdir(parents=True, exist_ok=True)
        probe = root / ".doctor-probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        writable = True
    except OSError:
        writable = False
    runs = RunStore(root).list()
    counts: dict[str, int] = {}
    for entry in runs:
        counts[entry["status"]] = counts.get(entry["status"], 0) + 1
    return {
        "root": str(root),
        "writable": writable,
        "version": __version__,
        "python": sys.version.split()[0],
        "runs": len(runs),
        "by_status": counts,
        "templates": templates(),
        "policy": Swarm(root).policy.to_context(),
    }


def _swarm(args: argparse.Namespace, root: Path) -> tuple[dict, int]:
    roster = parse_roster(_value(args.roster) if getattr(args, "roster", None) else None)
    swarm = Swarm(root, roster=roster)
    sub = args.swarm_command

    if sub == "templates":
        return {"templates": templates()}, OK

    if sub == "plan":
        template = choose_template(args.goal, swarm.policy, args.template)
        graph = build_graph(args.goal, template)
        if args.out:
            Path(args.out).write_text(json.dumps(graph, indent=2), encoding="utf-8")
            return {"template": template, "graph_id": graph["id"], "written": str(Path(args.out).resolve())}, OK
        return {"template": template, "graph": graph}, OK

    if sub == "open":
        run = swarm.open(
            args.goal,
            thread=args.thread,
            resource=args.resource,
            template=args.template,
            signal=_value(args.signal) if args.signal else None,
        )
        return run.to_dict(), OK

    if sub == "record":
        run = swarm.store.load(args.run)
        if run.is_terminal:
            raise Conflict(f"run {run.id} is {run.status}")
        swarm.record(run, args.step, _value(args.result))
        return run.to_dict(), OK

    run = swarm.store.load(args.run)
    if sub == "batch":
        return {
            "run_id": run.id,
            "status": run.status,
            "batch": [
                {
                    "id": step.id,
                    "agent": step.agent,
                    "instruction": step.instruction,
                    "meta": step.meta,
                    "context": swarm.context_for(run, step),
                }
                for step in swarm.batch(run)
            ],
        }, OK
    if sub == "consensus":
        return swarm.consensus(run, args.group), OK
    if sub == "verdict":
        return swarm.verdict(run), OK
    if sub == "recap":
        return {"recap": swarm.recap(run)}, OK
    raise ValueError(f"unknown swarm command: {sub}")


def _parser() -> argparse.ArgumentParser:
    # SUPPRESS keeps a subparser from writing its own default over a flag given before the
    # subcommand: without it `mai --root X doctor` silently falls back to the environment.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--root", default=argparse.SUPPRESS, help="store root; defaults to $MASTRA_ROOT or the Hermes home"
    )
    common.add_argument(
        "--pretty", action="store_true", default=argparse.SUPPRESS, help="indent the JSON output"
    )

    parser = argparse.ArgumentParser(prog="mastra-orchestrate", parents=[common])
    sub = parser.add_subparsers(dest="command", required=True)

    def add(name: str) -> argparse.ArgumentParser:
        return sub.add_parser(name, parents=[common])

    start = add("start")
    start.add_argument("--graph", required=True)
    start.add_argument("--thread", required=True)
    start.add_argument("--resource", required=True)
    start.add_argument("--signal")
    start.add_argument("--roster")
    start.add_argument("--id", dest="id")

    complete = add("complete")
    complete.add_argument("--run", required=True)
    complete.add_argument("--step", required=True)
    complete.add_argument("--result", required=True)

    for name in ("retry", "abort", "show", "status", "resume", "export", "events"):
        command = add(name)
        command.add_argument("--run", required=True)
        if name == "retry":
            command.add_argument("--step", required=True)
        if name == "abort":
            command.add_argument("--reason", default="")
        if name == "export":
            command.add_argument("--out")
        if name == "events":
            command.add_argument("--tail", type=int, default=0)

    listing = add("list")
    listing.add_argument("--status")
    listing.add_argument("--limit", type=int)

    for name in ("recall", "remember"):
        command = add(name)
        command.add_argument("--thread", required=True)
        command.add_argument("--resource", required=True)
        if name == "remember":
            command.add_argument("--working-memory")
            command.add_argument("--observation")
            command.add_argument("--summary")

    validate = add("validate")
    validate.add_argument("--graph", required=True)

    render = add("render")
    render.add_argument("--graph")
    render.add_argument("--run")
    render.add_argument("--format", choices=("mermaid", "ascii"), default="mermaid")

    add("doctor")

    swarm = add("swarm")
    swarm_sub = swarm.add_subparsers(dest="swarm_command", required=True)
    swarm_sub.add_parser("templates", parents=[common])

    plan = swarm_sub.add_parser("plan", parents=[common])
    plan.add_argument("--goal", required=True)
    plan.add_argument("--template")
    plan.add_argument("--out")

    open_run = swarm_sub.add_parser("open", parents=[common])
    open_run.add_argument("--goal", required=True)
    open_run.add_argument("--thread", required=True)
    open_run.add_argument("--resource", required=True)
    open_run.add_argument("--template")
    open_run.add_argument("--signal")
    open_run.add_argument("--roster")

    for name in ("batch", "verdict", "recap"):
        command = swarm_sub.add_parser(name, parents=[common])
        command.add_argument("--run", required=True)

    record = swarm_sub.add_parser("record", parents=[common])
    record.add_argument("--run", required=True)
    record.add_argument("--step", required=True)
    record.add_argument("--result", required=True)
    record.add_argument("--roster")

    consensus = swarm_sub.add_parser("consensus", parents=[common])
    consensus.add_argument("--run", required=True)
    consensus.add_argument("--group", required=True)
    consensus.add_argument("--roster")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    root = Path(args.root).expanduser() if getattr(args, "root", None) else default_root()
    try:
        payload, code = _dispatch(args, root)
    except Conflict as exc:
        return _fail(str(exc), CONFLICT)
    except GraphError as exc:
        return _fail("invalid graph", INVALID, problems=exc.problems)
    except FileNotFoundError as exc:
        return _fail(str(exc), MISSING)
    except KeyError as exc:
        return _fail(f"unknown step: {exc.args[0] if exc.args else ''}", MISSING)
    except (ValueError, json.JSONDecodeError) as exc:
        return _fail(str(exc), INVALID)
    _emit(payload, getattr(args, "pretty", False))
    return code


if __name__ == "__main__":
    sys.exit(main())
