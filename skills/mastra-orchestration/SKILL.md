---
name: mastra-orchestration
description: Orchestrate sub-agent swarms with a persisted graph.
version: 2.0.0
author: imanujela
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [orchestration, swarm, supervisor, workflow, memory, sub-agent]
    related_skills: [hermes-agent]
---

# Mastra orchestration

You are the supervisor. `mastra-orchestrate` owns the run; Hermes sub-agents do the work. One run,
one ready batch per turn, one recorded result per worker.

The CLI is JSON-only. Read `id`, `status`, `ready`, and the `batch[].context` field; ignore the rest.

## When to Use

- The user asks for multi-agent work, a swarm, a supervisor, or a Mastra-style workflow.
- `mai swarm batch --run <id>` returns steps still owed by an open run.

A request that does not split across workers is a single task, not a swarm.

## Prerequisites

`mai` on PATH (`uv tool install --editable <repo>`), or run it as `python -m mastra_ai_agents`.

## Procedure

1. **Health.** `mai doctor --pretty` → `root`, `writable: true`. Done when both are printed.
2. **Recall the thread.** `mai recall --thread <t> --resource <r>`. Done when `working_memory`,
   `observations` and `summary` are in hand. An empty recall on a new thread is a complete answer.
3. **Open.** `mai swarm open --goal "<goal>" --thread <t> --resource <r>`. Done when the print has
   `id`, `graph_id` and a non-empty `ready`. To inspect the plan first, `mai swarm plan --goal ...`
   and pass `--out` a file.
4. **Dispatch the batch.** `mai swarm batch --run <id>`; every entry's `context` goes to a child
   verbatim. One `delegate_task` call per batch — parallel lanes in separate calls lose the parallel
   node. Done when every `id` in `batch` has a summary. When the batch exceeds four lanes, send
   successive calls of four; concurrency is the dispatcher's cap, not the graph's.
5. **Record.** `mai swarm record --run <id> --step <sid> --result '<json>'` per summary, carrying
   `text` plus any `signal` the worker produced. Use the exact id from `batch` — a `foreach` copy is
   `<id>#<i>`, a `loop` copy is `<id>#r<n>`. `bail` is terminal: stop dispatching. `error` spends a
   retry. Done when the print is terminal or carries a new `ready` batch.
6. **Judge.** When a group of lanes answered independently, run
   `mai swarm consensus --run <id> --group <group>`. Done when `winner` and `dissent` are in hand;
   report the dissent, do not bury it.
7. **Repeat** steps 4–6 while `status` is `running`. Done when status is `done`, `bailed`, `failed`
   or `aborted`.
8. **Close.** `mai swarm verdict --run <id>` and `mai swarm recap --run <id>`. Then
   `mai remember --thread <t> --resource <r> --working-memory '<json>' --observation '<one line>'`.
   Done when `recall` prints that observation.

## Pitfalls

- A child sees only the `context` you pass, never this conversation. Extra paraphrase loses the
  instruction's exact wording; pass the field through.
- Two dispatches for one batch double the work and hide the parallel node.
- `bail` and `failed` are terminal. `retry` and `abort` refuse a terminal run with exit code 4.
- A stuck lane is a `retry` or a `reopen`, never a hand-edited run file.
- Windows: pass `C:/...` forward-slash paths; an MSYS `/tmp` path is not one the CLI can open.
- In bash, single-quote `--result` and double-quote the JSON inside.
- `swarm consensus` reads `outputs`; record every lane first, or the vote is over a partial field.

## Verification

- The run is real when `mai status --run <id>` prints a terminal status.
- A worker claim is real when `record` accepted that step id and `swarm verdict` counts it in
  `steps_completed`.
- A consensus is real when `swarm consensus` printed `support` and `agreement` for that group.

Schema: `references/graph.md`. Design: `docs/swarm.md` in the repo.
