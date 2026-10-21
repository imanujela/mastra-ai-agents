# Graph schema (v2)

A graph is one JSON object. `chain` is an ordered list of nodes; each node is one op. v1 graphs
(`then`, `parallel`, `branch`) run unchanged.

```json
{
  "id": "content",
  "roster": { "writer": { "own_memory": true } },
  "chain": [ { "op": "then", "step": { "id": "research", "agent": "researcher", "instruction": "Find three sources." } } ]
}
```

| Field | Required | Meaning |
| --- | --- | --- |
| `id` | yes | Non-empty string. Copied onto every `Run` as `graph_id`. |
| `chain` | yes | Non-empty list of nodes. |
| `roster` | no | `{ "<agent>": { "own_memory": bool } }`. Unknown agents default to `own_memory: false`. |

## Ops

| op | Shape | Readied when |
| --- | --- | --- |
| `then` | `{"op":"then","step":<step>}` | the previous node settled |
| `parallel` | `{"op":"parallel","steps":[<step>, ...]}` | every step at once; the next node waits for all of them |
| `branch` | `{"op":"branch","cases":[{"when":{k:v},"step":<step>}],"default":<step>}` | every case whose `when` is a subset of the run signal; `default` only when no case matched; otherwise the node is skipped |
| `foreach` | `{"op":"foreach","over":"key","steps":[<step>...],"max_parallel":4}` | one copy of each block step per item in `signal[key]` |
| `loop` | `{"op":"loop","steps":[<step>...],"until":{k:v},"max_iterations":3}` | the block, repeated until the signal matches `until` or the cap is reached |

### Step

```json
{ "id": "dig", "agent": "scout", "instruction": "Research {{item}}.",
  "retries": 1, "timeout_s": 600, "meta": { "lane": "sources" } }
```

| Field | Required | Default | Meaning |
| --- | --- | --- | --- |
| `id` | yes | — | Unique across the whole graph, nested blocks included. |
| `agent` | yes | — | Worker name. The dispatcher maps it to a sub-agent. |
| `instruction` | yes | — | The prompt body the worker receives. |
| `retries` | no | `0` | Extra attempts after an `error` result. |
| `timeout_s` | no | none | Advisory budget for the dispatcher. |
| `meta` | no | `{}` | Free-form, carried through to the dispatched step. |

`memory_thread` and `resource` are not authored. The engine fills them from the run plus the
roster: a worker with `own_memory: true` gets `null` for both, so it starts clean.

## Runtime ids

`foreach` copies become `<id>#<item-index>`; `loop` copies become `<id>#r<iteration>`. The base id
stays unique in the graph, and every copy gets its own slot in `outputs` and `attempts`.

## Results a worker returns

| Key | Effect |
| --- | --- |
| `text` | the worker's answer; kept in `outputs[step_id]` |
| `signal` | dict merged into `run.signal`; later branches, loops and foreach reads see it |
| `bail` | truthy ends the run as `bailed`; no further step is readied |
| `error` | truthy counts an attempt: re-readied while `attempts <= retries`, else the run ends `failed` |

Example: `examples/research-swarm.json` uses all five ops. Validate it with
`mastra-orchestrate validate --graph examples/research-swarm.json`.
