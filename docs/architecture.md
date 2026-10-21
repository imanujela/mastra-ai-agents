# Architecture contract

v1.0 rewrite of the 0.1 supervisor. Python 3.11+, **standard library only**. Library modules
return data and raise; only `cli.py` prints. Every module imports its types from `types.py`.

## Modules and the exact API each one must expose

| File | Owner workstream | Public surface |
| --- | --- | --- |
| `types.py` | locked, do not edit | `Step`, `Run`, `Recall`, status constants, `utc_now()` |
| `graph.py` | A | `parse_graph(raw) -> dict`, `iter_ops(chain)`, `step_ids(chain) -> list[str]` |
| `validate.py` | A | `validate_graph(raw) -> list[str]` (empty = ok), `class GraphError(ValueError)` |
| `roster.py` | B | `parse_roster(raw) -> dict`, `resolve_step(raw_step, run, roster) -> Step` |
| `engine.py` | B | `Orchestrator(roster=None)`, `.start(graph, thread, resource, signal=None) -> Run`, `.complete(run, step_id, result) -> Run`, `.retry(run, step_id) -> Run`, `.abort(run, reason="") -> Run` |
| `store.py` | C | `RunStore(root)`, `.save(run) -> Path`, `.load(run_id) -> Run`, `.list(status=None, limit=None) -> list[dict]`, `.delete(run_id) -> bool`, `.exists(run_id) -> bool` |
| `events.py` | C | `EventLog(runs_dir)`, `.append(run_id, event, **fields) -> dict`, `.read(run_id) -> list[dict]` |
| `memory.py` | C | `Memory(root)`, `.remember(thread, resource, working_memory=None, observation=None, summary=None) -> Recall`, `.recall(thread, resource) -> Recall`, `.forget(thread, resource) -> bool`, `.threads(resource=None) -> list[dict]` |
| `blackboard.py` | C | `Blackboard(root)`, `.post/.entries/.digest/.prune` |
| `consensus.py` | C | `vote(results, key)`, `rank(results, key)`, `merge(results, strategy, key)` |
| `policy.py` | C | `Policy(path)`, `.observe(template, outcome)`, `.rank(templates)`, `.snapshot()`, `.to_context()` |
| `swarm.py` | E | `Swarm(root, roster=None, policy_path=None)` with `.plan/.open/.batch/.context_for/.record/.consensus/.group_ids/.verdict/.recap/.learn`; `build_graph(goal, template)`, `choose_template(goal, policy, preferred)`, `templates()` |
| `render.py` | D | `to_mermaid(graph) -> str`, `run_mermaid(run) -> str`, `to_ascii(graph) -> str` |
| `cli.py` | D | `main(argv=None) -> int` |
| `__init__.py` | D | re-export `Orchestrator`, `Run`, `Step`, `Memory`, `RunStore`, `Recall`, `__version__` |

## Graph schema v2

One JSON object: `{"id": str, "chain": [node, ...], "roster": {...}?}`. v1 graphs stay valid.

| op | shape | ready when |
| --- | --- | --- |
| `then` | `{"op":"then","step":<step>}` | previous node settled |
| `parallel` | `{"op":"parallel","steps":[<step>...]}` | all steps at once; next node waits for all |
| `branch` | `{"op":"branch","cases":[{"when":{k:v},"step":<step>}],"default":<step>?}` | cases whose `when` is a subset of the run signal; `default` when none matched |
| `foreach` | `{"op":"foreach","over":"key","steps":[<step>...],"max_parallel":int?}` | one batch of step copies per list item in `signal[key]`; ids become `<id>#<i>`; `{{item}}` in `instruction` is substituted |
| `loop` | `{"op":"loop","steps":[<step>...],"until":{k:v},"max_iterations":int}` | block repeats; stops when signal matches `until` or the cap is hit |

A step is `{"id","agent","instruction"}` plus optional `retries` (int, default 0),
`timeout_s` (int), `meta` (dict). Ids must be unique across the graph.

Worker results: `{"text": str}` plus optional `"signal": {dict}` (merged), `"bail": true`
(run ends `bailed`), `"error": str` (attempt counted, step re-ready while attempts <= retries,
else run `failed`).

## Invariants

- `Run` is fully serializable: round-trip `Run.from_dict(run.to_dict()) == run` by field values.
- Store writes are atomic (`tmp` file + `os.replace`); a crash never leaves a half run.
- Memory writes use the same atomic path.
- No module except `cli.py` writes to stdout.
- No third-party dependency, no network, no git in tests.
