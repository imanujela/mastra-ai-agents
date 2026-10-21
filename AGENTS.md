# AGENTS.md

Agent-facing guide to this repo. The contract a module must satisfy is
[`docs/architecture.md`](docs/architecture.md); read it before editing `src/`.

## Run things

```bash
python -m pytest                 # whole suite; conftest puts src/ on sys.path
python -m pytest tests/test_engine_core.py
python -m ruff check .
mastra-orchestrate doctor --pretty
```

No install step is needed for tests. Standard library only — a new dependency is a rejected change,
not a review comment.

## The shape of the code

| Path | Holds |
| --- | --- |
| `src/mastra_ai_agents/types.py` | `Step`, `Run`, `Recall`, status constants — frozen, imported by everything |
| `graph.py` / `validate.py` | parse and validate a graph; errors carry a JSON path |
| `roster.py` | `own_memory` resolution, so a worker either joins the run's thread or starts clean |
| `engine.py` | the state machine: readiness, retries, bail, abort. No I/O. |
| `store.py` / `events.py` / `memory.py` | durable state: atomic run files, JSONL audit, thread memory |
| `blackboard.py` | the run's shared field — what the swarm already knows, read by the next wave |
| `consensus.py` / `policy.py` | deterministic judgement, and the cross-run learning the next plan reads |
| `swarm.py` | planning, per-child context, consensus, verdict. Composes the engine; the engine never imports it |
| `render.py` / `cli.py` | output edges; `cli.py` is the only module allowed to print |

## Invariants

- `Run` round-trips through `to_dict()`/`from_dict()` by field values. A new field is added to both,
  plus a test, or not at all.
- Every state mutation refreshes `run.updated_at`.
- Every write is atomic: `.tmp` in the same directory, then `os.replace`. A reader never sees a torn
  file.
- Family-level empty nodes (`branch` with no match, `foreach` over an empty list) advance the chain
  silently; they never appear in `ready`.
- `engine.py` does not import `store`, `events`, or `memory`. The CLI composes them.
- Tests use `tmp_path`; nothing writes under a real home directory.

## Definition of done

A change lands when every one of these holds:

- `python -m pytest` is green, including tests for the new behaviour that failed before the change.
- `python -m ruff check .` is clean.
- `docs/` still matches the code for any surface the change touched (`graph.md` for ops and fields,
  `cli.md` for commands and exit codes, `architecture.md` for signatures).
- `examples/*.json` still validate: `mastra-orchestrate validate --graph <file>`.
