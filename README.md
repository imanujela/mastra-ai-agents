# mastra-ai-agents

An ASI swarm orchestrator for Hermes sub-agents. You hand it a goal. It expands the goal into a
workflow graph, tells you which steps are ready, folds each worker's result back into a persisted
run, judges independent lanes by consensus, and writes what it learned into a policy the next run
reads.

That is the whole mechanism: **goal → plan → waves → verdict → policy**. Nothing in the loop asks a
model to hold state in its head; the state is on disk, so a run survives a crashed turn, a new
session, or a different agent driving it.

The four originating ideas come from [mastra-ai/mastra](https://github.com/mastra-ai/mastra) at
`9360b34b` — agent rosters, `.then`/`.parallel`/`.branch` workflows, working plus observational
memory, and `bail()`. This is a Python runtime for dispatching those shapes to sub-agents; it does
not vendor the TypeScript framework.

## Install

```bash
uv tool install --editable .
mastra-orchestrate doctor --pretty
```

`mastra-orchestrate` and `mai` are the same entry point. Python 3.11+, standard library only.

## Drive a swarm

```bash
# 1. a goal becomes a graph; the template comes from the goal, the policy breaks ties
mai swarm plan --goal "audit the security of the export path" --pretty

# 2. open a run
mai swarm open --goal "compare Postgres and SQLite for this workload and decide" \
  --thread db-choice --resource user --pretty

# 3. take the ready batch, context included
mai swarm batch --run 8c21... --pretty

# 4. record each worker result; the run and the blackboard update together
mai swarm record --run 8c21... --step case-a --result '{"text":"Postgres","signal":{"lean":"pg"}}'

# 5. judge the independent lanes, then total the run
mai swarm consensus --run 8c21... --group debate --pretty
mai swarm verdict --run 8c21... --pretty
mai swarm recap --run 8c21...
```

Every command prints one JSON object. `swarm batch` is the only call a dispatcher needs: it carries
each ready step's instruction, its `meta.item` for a `foreach` copy, the run's prior outputs, the
blackboard digest, and the current policy line. Hand that `context` field to `delegate_task` and the
child needs nothing else from your conversation.

## The layers

| Layer | Module | What it owns |
| --- | --- | --- |
| Graph | `graph.py` / `validate.py` | parsing, normalisation, JSON-path error messages |
| Engine | `engine.py` | readiness, retries, bail, abort, loop iterations — every state transition |
| Swarm | `swarm.py` | templates, planning, per-step context, consensus, verdict, learning |
| Field | `blackboard.py` | stigmergic artifacts: what the swarm already knows, per run |
| Judgement | `consensus.py` | vote, rank, merge — deterministic, dissent preserved |
| Policy | `policy.py` | smoothed success rate per template, read by the next plan |
| State | `store.py` / `events.py` / `memory.py` | atomic run files, JSONL audit, thread memory |

## Templates

`swarm plan` picks one from the goal's keywords, then lets the policy separate ties.

| Template | Shape | Fits |
| --- | --- | --- |
| `research-sweep` | plan → `foreach` dig → parallel weigh/gaps → merge → `loop` critique/revise → `branch` ship | open questions that need sources |
| `build-feature` | recon → parallel design/risks → implement → verify → `branch` ship/repair | changes to a codebase |
| `review-sweep` | parallel correctness/security/clarity → judge → `branch` approve/patch | audits with a verdict |
| `debate` | parallel three cases → judge | decisions with live tradeoffs |
| `blank` | one step | a task that does not split |

Pass `--template` to override. Graphs are plain JSON: [`docs/graph.md`](docs/graph.md).

## Five ops, one step shape

| op | Effect |
| --- | --- |
| `then` | one step after the previous node |
| `parallel` | every step at once; the next node waits for all |
| `branch` | cases whose `when` is a subset of the signal; `default` when none match |
| `foreach` | one copy per item in `signal[key]`, `{{item}}` substituted, ids `#0`, `#1` |
| `loop` | repeat a block until the signal matches `until`, capped by `max_iterations` |

Workers return `text`, `signal`, `bail`, `error`. `signal` feeds later branches, loops and
`foreach` reads. `error` spends a retry; exhaustion ends the run `failed`. `bail` ends it `bailed`.

## What makes it a swarm, not a queue

- **A blackboard, not a transcript.** Every result posts to `<root>/blackboard/<run>.json`; the next
  wave's context carries the digest. A worker that never saw its sibling still inherits its finding.
- **Consensus with dissent.** Independent lanes answer separately, then `swarm consensus` votes.
  Minority answers stay in `dissent` — a disagreement is evidence, not noise.
- **A policy that learns.** Every terminal run updates a smoothed success rate per template.
  `swarm plan` consults it, so a template that keeps failing stops being chosen without a code edit.
- **Durable state.** Runs, artifacts and memory are written atomically (`tmp` + `os.replace`) and
  audited in JSONL. `resume`, `status` and `events` work from any new process.

## Commands

| Group | Commands |
| --- | --- |
| swarm | `plan`, `open`, `batch`, `record`, `consensus`, `verdict`, `recap`, `templates` |
| run | `start`, `complete`, `status`, `show`, `resume`, `list`, `retry`, `abort` |
| memory | `remember`, `recall` |
| inspect | `validate`, `render`, `events`, `export`, `doctor` |

Exit codes: `0` done, `2` invalid, `3` missing, `4` the run's status forbids it.
Full reference: [`docs/cli.md`](docs/cli.md). Module contract: [`docs/architecture.md`](docs/architecture.md).

## Use it from an agent

`skills/mastra-orchestration/` is the skill pack — the procedure for driving this CLI from Hermes
with `delegate_task`. Install it into a Hermes home:

```bash
python scripts/install_skill.py --force
```

It prints the installed path and keeps the previous copy beside it as `.bak-<utc>`.

## Layout

```
src/mastra_ai_agents/   types, graph, validate, roster, engine, store, events, memory,
                        blackboard, consensus, policy, swarm, render, cli
tests/                  one file per module, behaviour tests through the public interface
examples/               content.json, research-swarm.json, roster.json
docs/                   architecture contract, graph schema, CLI reference, swarm design
skills/                 the installable skill pack
scripts/install_skill.py
```

MIT.
