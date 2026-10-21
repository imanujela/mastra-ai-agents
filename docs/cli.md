# CLI

`mastra-orchestrate` (alias `mai`) prints one JSON object per call on stdout. `--pretty` indents
it; `--root` moves the store. Errors print `{"error": "..."}` and set the exit code.

| Exit | Meaning |
| --- | --- |
| 0 | the command did what it says |
| 2 | invalid usage, invalid graph, or a result that cannot be applied |
| 3 | unknown run, step, or thread |
| 4 | the run is already terminal and cannot accept that transition |

Root resolution, in order: `--root`, `$MASTRA_ROOT`, `$HERMES_HOME/mastra-orchestration`,
`%LOCALAPPDATA%/hermes/mastra-orchestration` on Windows, else
`~/.local/share/hermes/mastra-orchestration`.

## Run lifecycle

```bash
mastra-orchestrate start --graph examples/content.json --thread t1 --resource user
mastra-orchestrate complete --run <run_id> --step research --result '{"text":"3 sources","signal":{"length":"short"}}'
mastra-orchestrate status --run <run_id>
mastra-orchestrate show --run <run_id>
mastra-orchestrate list --status running --limit 5
mastra-orchestrate resume --run <run_id>
mastra-orchestrate retry --run <run_id> --step <step_id>
mastra-orchestrate abort --run <run_id> --reason "brief changed"
```

| Command | Does | Prints |
| --- | --- | --- |
| `start` | validates the graph, saves a new run, logs `started` | the run plus `ready` |
| `complete` | records a worker result and readies the next batch | the run plus `ready` |
| `status` | reads the saved run | `id`, `status`, `index`, `ready`, `outputs` count |
| `show` | reads the saved run whole | the full run object |
| `list` | index summaries, newest first | `runs` list |
| `resume` | re-prints the pending batch without mutating | the run plus `ready` |
| `retry` | clears attempts and outputs for one step, re-readies it | the run plus `ready` |
| `abort` | ends the run as `aborted` | the run |

`start` accepts `--signal '{"k":"v"}'`, `--roster '{"writer":{"own_memory":true}}'` or
`--roster roster.json`, and `--id <run_id>` to pin the id.

`complete` accepts `--result` as inline JSON or as a path to a JSON file.

## Swarm

```bash
mai swarm templates
mai swarm plan --goal "audit the security of the export path" [--template T] [--out graph.json]
mai swarm open --goal "compare X and Y and decide" --thread t1 --resource user [--template T] [--signal JSON] [--roster JSON|file]
mai swarm batch --run <id>
mai swarm record --run <id> --step <sid> --result '<json>'
mai swarm consensus --run <id> --group <group>
mai swarm verdict --run <id>
mai swarm recap --run <id>
```

| Command | Does | Prints |
| --- | --- | --- |
| `templates` | lists the planning templates | `templates` |
| `plan` | expands a goal into a graph, writes it with `--out` | `template`, `graph` or `written` |
| `open` | plans and starts a run in one call | the run, with its first `ready` batch |
| `batch` | the ready steps, each with its full child `context` | `batch[]` of `id`, `agent`, `instruction`, `meta`, `context` |
| `record` | folds a result in, posts it to the blackboard, updates the policy on a terminal run | the run |
| `consensus` | votes the outputs of one `consensus_group` | `winner`, `support`, `agreement`, `dissent`, `ids` |
| `verdict` | totals a run | `template`, `status`, `steps_completed`, `artifacts`, `risks`, `policy` |
| `recap` | one readable block | `recap` |

`swarm batch` is the dispatcher's whole input: pass `context` to the child verbatim. A `foreach`
step's copy is `<id>#<i>`; a `loop` copy is `<id>#r<n>`; `record` wants the exact id from `ready`.

## Memory

```bash
mastra-orchestrate remember --thread t1 --resource user \
  --working-memory '{"tone":"plain"}' --observation "prefers short drafts"
mastra-orchestrate recall --thread t1 --resource user
```

`remember` merges working memory, appends one timestamped observation (200 kept), and replaces
the summary when `--summary` is passed. `recall` prints `working_memory`, `observations`, and
`summary`.

## Inspect

```bash
mastra-orchestrate validate --graph examples/research-swarm.json
mastra-orchestrate render --graph examples/content.json --format mermaid
mastra-orchestrate render --run <run_id> --format mermaid
mastra-orchestrate render --graph examples/content.json --format ascii
mastra-orchestrate events --run <run_id> --tail 20
mastra-orchestrate export --run <run_id> --out run.json
mastra-orchestrate doctor
```

`validate` prints `{"valid": true}` or `{"valid": false, "problems": [...]}` and exits 2 on
problems. `doctor` prints the resolved root, whether it is writable, the Python version, and run
counts by status.

## Events

Every mutating command appends to `<root>/runs/<run_id>.events.jsonl`: `started`, `completed`,
`retry`, `aborted`, `bailed`, `failed`. `events --tail N` reads the last N lines.
