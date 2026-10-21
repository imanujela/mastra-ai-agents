# Changes

## 2.0.0 — ASI swarm orchestrator

The 0.1 package was a 508-line dispatcher: three ops, one JSON file per run, no failure model, no
audit trail, private attributes (`_chain`, `_index`, `_pending`) leaking into the saved payload.
The rewrite kept the supervisor core and added the layer that makes it a swarm: a goal expands into
a graph, the graph runs in waves, independent lanes are judged, and the run teaches the next plan.

### Added

- **Swarm layer (`swarm.py`).** `plan` expands a goal into a graph from five named templates
  (`research-sweep`, `build-feature`, `review-sweep`, `debate`, `blank`); `open` starts a run;
  `context_for` composes a child's whole context — instruction, `meta.item`, prior outputs,
  blackboard digest, policy line; `verdict` totals a run; `recap` renders it; `learn` feeds the
  policy.
- **Blackboard (`blackboard.py`).** Stigmergic artifact ledger per run: `post`, `entries` (tag/kind
  filters), `digest` (bounded context block), `prune`. Atomic writes; a corrupt board raises instead
  of silently truncating.
- **Consensus (`consensus.py`).** `vote` (case/whitespace-normalised, majority, dissent kept),
  `rank` (score, stable on ties), `merge` (`best` or `vote`). Deterministic, so a run replays.
- **Policy (`policy.py`).** Smoothed success rate per template, atomic JSON, corrupt file resets
  instead of blocking a run. `rank` orders candidate templates; `to_context` gives one line.
- **Swarm CLI.** `swarm plan|open|batch|record|consensus|verdict|recap|templates`, plus `doctor`
  reporting the resolved root, writability, version and run counts.
- **Graph v2:** `foreach` fan-out over `signal[key]` with `{{item}}` substitution and `#<i>` ids,
  `loop` blocks with `until` and `max_iterations`, per-branch `default`, per-step `retries`,
  `timeout_s`, `meta`.
- **Failure model:** `error` spends a retry and re-readies the step; exhaustion ends the run
  `failed` with the cause in `note`; `bail` ends it `bailed`; `abort` ends it `aborted`.
- **Atomic persistence:** `RunStore` writes `<id>.json.tmp` then `os.replace`, keeps a self-healing
  `runs/index.json`, and knows `save/load/list/latest/delete/exists`.
- **Event log:** `<root>/runs/<id>.events.jsonl`, append-only, torn-tail tolerant.
- **Thread memory v2:** shallow-merged working memory, timestamped observations capped at 200,
  replaceable summary, `forget`, `threads`, all atomic.
- **Rendering:** Mermaid for a graph or a live run (done/active/failed classes) and an ASCII tree.
- **Skill pack** at `skills/mastra-orchestration/` plus `scripts/install_skill.py`, a transactional
  installer that backs the previous copy up as `.bak-<utc>`.
- **Docs and CI:** `docs/architecture.md`, `docs/graph.md`, `docs/cli.md`, `docs/swarm.md`,
  `AGENTS.md`, a 164-test pytest suite, ruff, and a 3.11/3.12/3.13 workflow.

### Breaking

- **Renamed.** `mastra-orchestration` / `mastra_orchestration` → `mastra-ai-agents` /
  `mastra_ai_agents`. The console script `mastra-orchestrate` is unchanged; `mai` is a new alias.
- **Run files carry public fields.** `chain`, `index`, `pending`, `iterations`, `attempts`,
  `graph_id`, `roster`, `note`, `created_at`, `updated_at` — all round-trip through
  `to_dict()`/`from_dict()`. 0.1 files are history, not resumable state.
- **`Memory.recall()` returns timestamped observations.** `Recall.observations` is
  `[{"ts", "text"}]`; `Recall.texts` gives plain strings; legacy string observations are read.
- **`Orchestrator.complete()` raises `KeyError`** for an unknown or settled step;
  `retry`/`abort` reject terminal runs with `ValueError`.
- **The CLI is JSON-only.** One object per call, `--pretty` for indentation, exit codes 0/2/3/4.

### Changed

- `Run` owns `created_at`/`updated_at`, refreshed on every transition.
- Roster `own_memory` resolves once per step, so an own-memory worker gets
  `memory_thread=None`/`resource=None` rather than the parent's thread id.
- `Orchestrator.start()` stores the resolved roster on the run, so a later `complete` in a fresh
  process resolves the next batch identically.
- Empty nodes (`branch` with no match, `foreach` over an empty list) advance the chain silently.
- Default store root: `$MASTRA_ROOT`, then `$HERMES_HOME/mastra-orchestration`, then
  `%LOCALAPPDATA%/hermes/mastra-orchestration`, then `~/.local/share/hermes/mastra-orchestration`.

### Removed

- The `mastra_orchestration` package, its single-file CLI, and the non-atomic memory writer. No
  compatibility shim ships; 0.1 was never published.

## 0.1.0 — baseline

Four Mastra concepts reimplemented as a CLI: roster, `then`/`parallel`/`branch`, working plus
observational memory, `bail`. 508 lines including tests.
