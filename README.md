# Mastra orchestration

Rewrite of four systems from [mastra-ai/mastra](https://github.com/mastra-ai/mastra) at `9360b34b`, checked out at `Downloads/mastra`. This package is the installable supervisor. It does not vendor the TypeScript framework.

| Mastra | Here |
| --- | --- |
| `Agent.agents` supervisor roster | `roster` on `Orchestrator`; workers are Hermes sub-agents |
| workflow `.then` / `.parallel` / `.branch` | `chain` ops of the same names |
| working memory + observational memory | `Memory.remember` / `Memory.recall` on a thread |
| delegation `bail()` | a worker result with `"bail": true` stops the run |

Install: `uv tool install --editable .` from this directory, then `mastra-orchestrate --help`.
