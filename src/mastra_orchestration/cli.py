"""Persist a supervisor run so a later turn can record a worker result."""

import argparse
import json
import uuid
from pathlib import Path

from mastra_orchestration import Orchestrator, Run, Step


def start_run(root, graph, thread, resource, signal=None, roster=None):
    run = Orchestrator(roster=roster).start(graph, thread=thread, resource=resource, signal=signal)
    run_id = uuid.uuid4().hex[:12]
    payload = _snapshot(run, run_id)
    _write(root, payload)
    return payload


def complete_run(root, run_id, step_id, result):
    payload = json.loads(_path(root, run_id).read_text(encoding="utf-8"))
    run = _restore(payload)
    Orchestrator().complete(run, step_id, result)
    updated = _snapshot(run, run_id)
    _write(root, updated)
    return updated


def recall(root, thread, resource):
    from mastra_orchestration.memory import Memory

    found = Memory(Path(root) / "memory").recall(thread, resource)
    return {"working_memory": found.working_memory, "observations": found.observations}


def remember(root, thread, resource, working_memory=None, observation=None):
    from mastra_orchestration.memory import Memory

    Memory(Path(root) / "memory").remember(
        thread=thread,
        resource=resource,
        working_memory=working_memory,
        observation=observation,
    )
    return recall(root, thread, resource)


def _snapshot(run, run_id):
    return {
        "run_id": run_id,
        "status": run.status,
        "ready": [
            {
                "id": step.id,
                "agent": step.agent,
                "instruction": step.instruction,
                "memory_thread": step.memory_thread,
                "resource": step.resource,
            }
            for step in run.ready
        ],
        "outputs": run.outputs,
        "signal": run.signal,
        "thread": run.thread,
        "resource": run.resource,
        "chain": run._chain,
        "index": run._index,
        "pending": sorted(run._pending),
    }


def _restore(payload):
    return Run(
        ready=[Step(**step) for step in payload["ready"]],
        status=payload["status"],
        outputs=payload["outputs"],
        signal=payload["signal"],
        thread=payload["thread"],
        resource=payload["resource"],
        _chain=payload["chain"],
        _index=payload["index"],
        _pending=set(payload["pending"]),
    )


def _path(root, run_id):
    return Path(root) / "runs" / f"{run_id}.json"


def _write(root, payload):
    path = _path(root, payload["run_id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="mastra-orchestrate")
    parser.add_argument("--root", required=True)
    sub = parser.add_subparsers(dest="command", required=True)

    start = sub.add_parser("start")
    start.add_argument("--graph", required=True)
    start.add_argument("--thread", required=True)
    start.add_argument("--resource", required=True)
    start.add_argument("--signal", default="{}")
    start.add_argument("--roster", default="{}")

    done = sub.add_parser("complete")
    done.add_argument("--run", required=True)
    done.add_argument("--step", required=True)
    done.add_argument("--result", required=True)

    recalled = sub.add_parser("recall")
    recalled.add_argument("--thread", required=True)
    recalled.add_argument("--resource", required=True)

    noted = sub.add_parser("remember")
    noted.add_argument("--thread", required=True)
    noted.add_argument("--resource", required=True)
    noted.add_argument("--working-memory", default="{}")
    noted.add_argument("--observation", default="")

    args = parser.parse_args(argv)
    root = args.root
    if args.command == "start":
        graph = json.loads(Path(args.graph).read_text(encoding="utf-8"))
        payload = start_run(
            root,
            graph,
            thread=args.thread,
            resource=args.resource,
            signal=json.loads(args.signal),
            roster=json.loads(args.roster),
        )
    elif args.command == "complete":
        payload = complete_run(root, args.run, args.step, json.loads(args.result))
    elif args.command == "recall":
        payload = recall(root, args.thread, args.resource)
    else:
        payload = remember(
            root,
            args.thread,
            args.resource,
            working_memory=json.loads(args.working_memory),
            observation=args.observation or None,
        )
    print(json.dumps(payload))
    return 0
