# Workflow graph, shortest form

One JSON object: `{"id": str, "chain": [node, ...], "roster": {agent: {own_memory: bool}}?}`.
`chain` runs top to bottom. Validate with `mastra-orchestrate validate --graph <file>`.

| op | Shape | Ready when |
| --- | --- | --- |
| `then` | `{"op":"then","step":<step>}` | the node before it settled |
| `parallel` | `{"op":"parallel","steps":[<step>...]}` | all steps at once; next node waits for all |
| `branch` | `{"op":"branch","cases":[{"when":{k:v},"step":<step>}],"default":<step>}` | every case whose `when` is a subset of the signal; `default` when none matched; else skipped |
| `foreach` | `{"op":"foreach","over":"key","steps":[<step>...],"max_parallel":4}` | one copy per list item in `signal[key]` |
| `loop` | `{"op":"loop","steps":[<step>...],"until":{k:v},"max_iterations":3}` | the block, until the signal matches `until` or the cap |

Step: `{"id","agent","instruction"}` plus optional `retries` (int), `timeout_s` (int), `meta`
(object). Ids are unique across the graph, nested blocks included.

Result a worker returns: `{"text": "...", "signal": {...}, "bail": false, "error": "..."}`.
`signal` merges into the run and feeds later branches, loops and `foreach` reads. `bail` ends the
run. `error` spends a retry, then ends the run `failed`.

Runtime ids: `foreach` copy `<id>#<i>`, `loop` copy `<id>#r<n>`; `{{item}}` in the instruction is
substituted per copy.

```json
{"id":"content","chain":[
  {"op":"then","step":{"id":"research","agent":"researcher","instruction":"Find three sources."}},
  {"op":"parallel","steps":[
    {"id":"seo","agent":"analyst","instruction":"Check SEO. Return signal.length."},
    {"id":"tone","agent":"analyst","instruction":"Check tone."}]},
  {"op":"branch","cases":[
    {"when":{"length":"long"},"step":{"id":"deep","agent":"writer","instruction":"Long draft."}}],
   "default":{"id":"probe","agent":"analyst","instruction":"Pick a length."}}
]}
```

Working examples: `examples/content.json` (v1-compatible), `examples/research-swarm.json` (all five
ops), `examples/roster.json`.
