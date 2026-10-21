"""The swarm layer: a goal in, waves out.

Four rules make a wide fan-out usable instead of noisy:

1. A goal maps to a named template, so the shape of the work is inspectable before any worker runs.
2. Every result lands on the blackboard, so the next wave inherits what the swarm already knows.
3. Independent lanes can be judged by consensus, with the dissent kept.
4. A finished run updates the policy, so the next plan starts from the record rather than from zero.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .blackboard import Blackboard
from .consensus import vote
from .engine import Orchestrator
from .events import EventLog
from .graph import parse_graph
from .policy import Policy
from .roster import parse_roster
from .store import RunStore
from .types import TERMINAL, Run, Step

TEMPLATE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "research-sweep": ("research", "investigate", "sources", "survey", "brief", "landscape", "report"),
    "build-feature": ("build", "implement", "feature", "refactor", "fix", "ship", "migrate"),
    "review-sweep": ("review", "audit", "critique", "risk", "security", "qa", "regression"),
    "debate": ("decide", "compare", "choose", "tradeoff", "versus", "vs", "debate", "should we"),
    "blank": (),
}

DEFAULT_TEMPLATE = "research-sweep"


def templates() -> list[str]:
    return list(TEMPLATE_KEYWORDS)


def slug(text: str, limit: int = 40) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")
    return (cleaned or "goal")[:limit].strip("-")


def choose_template(goal: str, policy: Policy | None = None, preferred: str | None = None) -> str:
    """An explicit template wins; otherwise keyword hits, with the policy breaking ties."""
    if preferred:
        if preferred not in TEMPLATE_KEYWORDS:
            raise ValueError(f"unknown template {preferred!r}; known: {templates()}")
        return preferred

    lowered = f" {str(goal).lower()} "
    scored = {
        name: sum(1 for word in words if word in lowered)
        for name, words in TEMPLATE_KEYWORDS.items()
        if words
    }
    hits = [name for name, score in scored.items() if score]
    if not hits:
        return DEFAULT_TEMPLATE
    if len(hits) == 1:
        return hits[0]
    ordered = policy.rank(hits) if policy is not None else sorted(hits)
    return ordered[0]


def _step(step_id: str, agent: str, instruction: str, **extra: Any) -> dict[str, Any]:
    return {"id": step_id, "agent": agent, "instruction": instruction, **extra}


def build_graph(goal: str, template: str = DEFAULT_TEMPLATE) -> dict[str, Any]:
    """Expand a goal into a graph. Deterministic: same goal and template, same graph."""
    if template not in TEMPLATE_KEYWORDS:
        raise ValueError(f"unknown template {template!r}; known: {templates()}")
    graph_id = f"{template}:{slug(goal)}"
    chain: list[dict[str, Any]] = []

    if template == "blank":
        chain = [{"op": "then", "step": _step("answer", "researcher", str(goal))}]

    elif template == "research-sweep":
        chain = [
            {
                "op": "then",
                "step": _step(
                    "plan",
                    "scout",
                    "Split this goal into 3-5 search targets and return signal.targets as a list: "
                    f"{goal}",
                ),
            },
            {
                "op": "foreach",
                "over": "targets",
                "max_parallel": 4,
                "steps": [
                    _step(
                        "dig",
                        "researcher",
                        "Research {{item}} for the goal. Return signal.sources with two citations.",
                        retries=1,
                        timeout_s=600,
                    )
                ],
            },
            {
                "op": "parallel",
                "steps": [
                    _step(
                        "weigh",
                        "analyst",
                        "Weigh the sources gathered. Return signal.strength = strong or weak.",
                        meta={"consensus_group": "weigh"},
                    ),
                    _step(
                        "gaps",
                        "analyst",
                        "Name what the sources miss. Return signal.strength = strong or weak.",
                        meta={"consensus_group": "weigh"},
                    ),
                ],
            },
            {
                "op": "then",
                "step": _step(
                    "merge",
                    "writer",
                    "Merge the findings into one brief. Return signal.verdict = pass or revise.",
                    meta={"judge": "weigh"},
                ),
            },
            {
                "op": "loop",
                "until": {"verdict": "pass"},
                "max_iterations": 3,
                "steps": [
                    _step(
                        "critique",
                        "analyst",
                        "Score the brief. Return signal.verdict = pass or revise.",
                    ),
                    _step("revise", "writer", "Apply the critique and tighten the brief."),
                ],
            },
            {
                "op": "branch",
                "cases": [
                    {
                        "when": {"verdict": "pass"},
                        "step": _step("ship", "writer", "Finalise the brief and hand it back."),
                    }
                ],
                "default": _step(
                    "escalate", "analyst", "Report the unresolved gaps instead of shipping."
                ),
            },
        ]

    elif template == "build-feature":
        chain = [
            {
                "op": "then",
                "step": _step(
                    "recon",
                    "scout",
                    "Map the code this change touches and return signal.targets: " f"{goal}",
                ),
            },
            {
                "op": "parallel",
                "steps": [
                    _step("design", "engineer", "Propose the smallest design that satisfies the goal."),
                    _step("risks", "reviewer", "Name the failure modes this change can introduce."),
                ],
            },
            {
                "op": "then",
                "step": _step("implement", "engineer", "Implement the design against the recon targets."),
            },
            {
                "op": "then",
                "step": _step("verify", "reviewer", "Run the tests and return verdict = pass or fix."),
            },
            {
                "op": "branch",
                "cases": [
                    {
                        "when": {"verdict": "pass"},
                        "step": _step("ship", "engineer", "Commit the change and report what moved."),
                    }
                ],
                "default": _step("repair", "engineer", "Fix every failure the reviewer named."),
            },
        ]

    elif template == "review-sweep":
        chain = [
            {
                "op": "parallel",
                "steps": [
                    _step(
                        "correctness",
                        "reviewer",
                        "Review for defects. Return signal.verdict = clean or patch.",
                        meta={"consensus_group": "review"},
                    ),
                    _step(
                        "security",
                        "reviewer",
                        "Review for security and data loss. Return verdict = clean or patch.",
                        meta={"consensus_group": "review"},
                    ),
                    _step(
                        "clarity",
                        "reviewer",
                        "Review for naming, locality and dead code. Return verdict = clean or patch.",
                        meta={"consensus_group": "review"},
                    ),
                ],
            },
            {
                "op": "then",
                "step": _step(
                    "judge",
                    "analyst",
                    "Reconcile the three reviews. Return signal.verdict = clean or patch.",
                    meta={"judge": "review"},
                ),
            },
            {
                "op": "branch",
                "cases": [
                    {
                        "when": {"verdict": "clean"},
                        "step": _step("approve", "reviewer", "Approve with the evidence gathered."),
                    }
                ],
                "default": _step("patch", "engineer", "Apply the fixes the majority named."),
            },
        ]

    else:  # debate
        chain = [
            {
                "op": "parallel",
                "steps": [
                    _step(
                        "case-a",
                        "analyst",
                        "Argue the strongest case FOR the first option. Return signal.lean: " f"{goal}",
                        meta={"consensus_group": "debate"},
                    ),
                    _step(
                        "case-b",
                        "analyst",
                        "Argue the strongest case AGAINST it. Return signal.lean: " f"{goal}",
                        meta={"consensus_group": "debate"},
                    ),
                    _step(
                        "case-c",
                        "analyst",
                        "Argue the option nobody proposed. Return signal.lean: " f"{goal}",
                        meta={"consensus_group": "debate"},
                    ),
                ],
            },
            {
                "op": "then",
                "step": _step(
                    "judge",
                    "writer",
                    "Weigh the three cases. Return signal.verdict = pass once one side wins.",
                    meta={"judge": "debate"},
                ),
            },
        ]

    return {"id": graph_id, "chain": chain}


def template_of(graph_id: str) -> str:
    return str(graph_id).split(":", 1)[0]


class Swarm:
    """Composes the engine, the store, the blackboard and the policy into one surface."""

    def __init__(
        self,
        root: str | Path,
        roster: dict[str, dict[str, Any]] | None = None,
        policy_path: str | Path | None = None,
    ) -> None:
        self.root = Path(root)
        self.roster = parse_roster(roster)
        self.store = RunStore(self.root)
        self.events = EventLog(self.store.runs_dir)
        self.board = Blackboard(self.root)
        self.policy = Policy(policy_path or self.root / "policy.json")

    def plan(self, goal: str, template: str | None = None) -> dict[str, Any]:
        return parse_graph(build_graph(goal, choose_template(goal, self.policy, template)))

    def open(
        self,
        goal: str,
        thread: str,
        resource: str,
        template: str | None = None,
        signal: dict[str, Any] | None = None,
    ) -> Run:
        graph = self.plan(goal, template)
        run = Orchestrator(roster=self.roster).start(graph, thread=thread, resource=resource, signal=signal)
        run.roster = self.roster
        self.store.save(run)
        self.events.append(
            run.id,
            "swarm.started",
            template=template_of(run.graph_id),
            goal=str(goal)[:200],
            thread=thread,
            resource=resource,
        )
        return run

    def batch(self, run: Run) -> list[Step]:
        return list(run.ready)

    def context_for(self, run: Run, step: Step) -> str:
        """Everything a child needs to act, since a child sees none of this conversation."""
        parts = [f"Swarm step {step.id} (agent {step.agent}).", f"Instruction: {step.instruction}"]
        if step.meta.get("item") is not None:
            parts.append(f"Item: {json.dumps(step.meta['item'], ensure_ascii=False)}")
        group = step.meta.get("consensus_group")
        if group:
            parts.append(f"Independent lane of group {group}: answer from your own evidence, do not coordinate.")
        prior = {
            key: value.get("text")
            for key, value in run.outputs.items()
            if isinstance(value, dict) and value.get("text")
        }
        if prior:
            parts.append("Prior results: " + json.dumps(prior, ensure_ascii=False)[:800])
        digest = self.board.digest(run.id)
        if digest:
            parts.append(digest)
        parts.append(self.policy.to_context())
        return "\n".join(parts)

    def record(self, run: Run, step_id: str, result: dict[str, Any]) -> Run:
        """Fold one worker result in, publish it, and persist the run."""
        step = self._step_for(run, step_id)
        Orchestrator(roster=run.roster or self.roster).complete(run, step_id, result)
        if isinstance(result, dict):
            text = str(result.get("text") or "").strip()
            if text:
                self.board.post(
                    run.id,
                    step_id,
                    "result",
                    title=f"{step.agent if step else 'worker'} · {step_id}",
                    body=text,
                    tags=[step.agent] if step else [],
                )
            if result.get("error"):
                self.board.post(run.id, step_id, "risk", title=f"{step_id} failed", body=str(result["error"])[:500])
        self.store.save(run)
        if run.status in TERMINAL:
            self.events.append(run.id, f"run.{run.status}", step=step_id)
            self.learn(run)
        else:
            self.events.append(run.id, "step.completed", step=step_id, ready=len(run.ready))
        return run

    def group_ids(self, run: Run, group: str) -> list[str]:
        bases = [raw["id"] for raw in self._all_steps(run) if (raw.get("meta") or {}).get("consensus_group") == group]
        return [key for base in bases for key in self._keys_for(run, base)]

    def consensus(self, run: Run, group: str) -> dict[str, Any]:
        ids = self.group_ids(run, group)
        results = [run.outputs[key] for key in ids if isinstance(run.outputs.get(key), dict)]
        verdict = vote(results)
        self.board.post(
            run.id,
            f"judge:{group}",
            "consensus",
            title=f"{group}: {verdict['winner'] or 'no answer'}",
            body=json.dumps(verdict, ensure_ascii=False),
            tags=[group],
            score=verdict["agreement"],
        )
        return {"group": group, "ids": ids, **verdict}

    def verdict(self, run: Run) -> dict[str, Any]:
        artifacts = self.board.entries(run.id)
        return {
            "run_id": run.id,
            "template": template_of(run.graph_id),
            "status": run.status,
            "ready": run.ready_ids(),
            "steps_completed": len(run.outputs),
            "artifacts": len(artifacts),
            "risks": len([entry for entry in artifacts if entry["kind"] == "risk"]),
            "consensus": [entry["title"] for entry in artifacts if entry["kind"] == "consensus"],
            "policy": self.policy.to_context(),
        }

    def recap(self, run: Run) -> str:
        lines = [
            f"swarm {run.id} · {template_of(run.graph_id)} · {run.status}",
            f"steps completed: {len(run.outputs)} · ready: {', '.join(run.ready_ids()) or 'none'}",
        ]
        for entry in self.board.entries(run.id, kind="consensus"):
            lines.append(f"consensus {entry['title']}")
        for entry in self.board.entries(run.id, kind="risk")[:5]:
            lines.append(f"risk {entry['title']}")
        lines.append(self.policy.to_context())
        return "\n".join(lines)

    def learn(self, run: Run) -> dict[str, Any] | None:
        if run.status not in TERMINAL:
            return None
        return self.policy.observe(template_of(run.graph_id), run.status)

    @staticmethod
    def _all_steps(run: Run) -> list[dict[str, Any]]:
        raws: list[dict[str, Any]] = []
        for node in run.chain:
            op = node.get("op")
            if op == "then":
                raws.append(node["step"])
            elif op == "branch":
                raws.extend(case["step"] for case in node.get("cases", []))
                if node.get("default"):
                    raws.append(node["default"])
            else:
                raws.extend(node.get("steps", []))
        return raws

    def _step_for(self, run: Run, step_id: str) -> Step | None:
        for step in run.ready:
            if step.id == step_id:
                return step
        base = step_id.split("#", 1)[0]
        for raw in self._all_steps(run):
            if raw["id"] == base:
                return Step(
                    id=step_id,
                    agent=raw["agent"],
                    instruction=raw["instruction"],
                    meta=dict(raw.get("meta") or {}),
                )
        return None

    @staticmethod
    def _keys_for(run: Run, base: str) -> list[str]:
        keys = [key for key in run.outputs if key == base or key.startswith(f"{base}#")]
        return sorted(keys, key=lambda key: (key.split("#")[0] != base, key))
