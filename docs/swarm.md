# Swarm design

The engine executes a graph. The swarm layer decides what graph to build, what each child is told,
how independent answers are judged, and what the run teaches the next one.

## Goal to graph

`choose_template` scores the goal against keyword sets, then hands the tied candidates to
`Policy.rank`, which orders them by smoothed success rate. An explicit `--template` skips both steps.
`build_graph` is deterministic: the same goal and template produce the same graph, so a plan can be
reviewed before any worker runs and compared across sessions.

| Template | Nodes | Why it exists |
| --- | --- | --- |
| `research-sweep` | plan → foreach dig → parallel weigh/gaps → merge → loop critique/revise → branch ship/escalate | breadth first, then converge under a loop |
| `build-feature` | recon → parallel design/risks → implement → verify → branch ship/repair | the parallel node buys two independent views of the same change |
| `review-sweep` | parallel correctness/security/clarity → judge → branch approve/patch | three lanes never coordinate, so agreement means something |
| `debate` | parallel three cases → judge | forces the option nobody proposed into the field |
| `blank` | one step | a goal that does not split; also the control case in tests |

## What a child receives

`Swarm.context_for(run, step)` is the whole contract with a worker:

1. the step id, agent and instruction;
2. `meta.item` when the step is a `foreach` copy;
3. a note that it is an independent lane, when it carries a `consensus_group`;
4. prior outputs from the run (`text` only, capped at 800 chars);
5. the blackboard digest (newest 12 artifacts);
6. the policy line.

The worker returns `text` plus an optional `signal`. Nothing else crosses the boundary, which is why
the same graph can be dispatched by any agent on any machine.

## Blackboard

Every result posts as an artifact (`kind: result`), every error as a `risk`, every consensus as a
`consensus` entry. `digest` renders the newest N as one bounded block. This is the difference
between a fan-out and a swarm: a worker can use a finding it never saw produced.

`prune(keep=500)` exists for long-running threads; `digest` caps itself at 12 entries and 160 chars
per body so it cannot crowd out the instruction.

## Consensus

`vote` normalises case and whitespace, counts, and reports `winner`, `support`, `agreement`,
`dissent`. Ties go to the first result seen, so the outcome is replayable. The dissent list is the
point: it is the minority that a judge step or a human reads before acting.

## Policy

Each terminal run calls `Policy.observe(template, status)`. The stored rate is
`(successes + 1) / (attempts + 2)`, which keeps one lucky run from dominating and lets a failed
template recover. `rank` sorts by that rate, then by attempts, then by input order. A template that
never runs sits at 0.5 — neutral, never a penalty for being new.

The policy file is `<root>/policy.json`. A corrupt file resets to empty rather than blocking work:
losing learned weights is cheaper than refusing to plan.

## Invariants

- Planning is pure: no I/O, no randomness, no clock.
- Every result reaches the blackboard and the run in the same `record` call.
- Consensus is deterministic over its inputs.
- Policy updates happen only on a terminal status, and only once per run.
- The swarm layer composes the engine; the engine never imports the swarm.

## Failure modes and their handling

| Failure | Handling |
| --- | --- |
| a worker returns `error` | retries spent per step, then the run ends `failed` with the cause |
| a worker bails | run ends `bailed`; the blackboard keeps what was already learned |
| a template keeps failing | rate drops; the next plan prefers a different template |
| a lane never answers | run stays `running`; `resume` and `events` show what is owed |
| blackboard JSON is corrupt | `entries` raises with the path — refuse to invent findings |

## Extending

A new template is one branch in `build_graph` plus a keyword set in `TEMPLATE_KEYWORDS`, and it
enters the policy immediately as neutral. New judging rules belong in `consensus.py` as pure
functions; new context belongs in `context_for`, where every worker gets it at once.
