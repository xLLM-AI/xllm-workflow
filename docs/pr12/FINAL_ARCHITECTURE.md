# PR12 Final Skill Architecture

## Public Routing Layers

```text
User intent
  |
  +-- experiment state ----------> xllm-experiment-lifecycle
  |                                  -> xllm-flow control plane
  +-- model/PR history query ----> model-pr-optimization-history
  +-- open-ended optimization ---> xllm-npu-sota-loop
  +-- mixed evaluation ----------> xllm-npu-eval-runner
  +-- matrix/repeat campaign ----> xllm-npu-batch-perf
  +-- fair performance claim ----> xllm-npu-benchmark
  +-- one workload -------------> perf-runner / accuracy-runner
  +-- focused diagnosis --------> profiler / pipeline / accuracy-debug / incident
  +-- planning/development -----> capacity / compute / review / operator skills
  +-- direct maintenance -------> build-gate / server-manager / report-writer

Delegated implementation
  +-- ssh-remote-exec (internal; explicit invocation remains available)
  +-- xllm-flow fairness, evidence, checksum and projection functions/scripts
```

The lifecycle facade owns state transitions, not specialist implementation. SOTA owns only an
open-ended measurable optimization loop. Eval executes a mixed suite, benchmark owns policy and
conclusions, and narrow runners retain explicit one-workload routes.

`model-pr-optimization-history` is a public analyzer because history retrieval has an independent
goal, inputs and output. Its dossiers remain reference data under `reference/pr_history/`; SOTA uses
the skill during Learn but does not own direct history queries.

## Catalog Consumption Boundary

`skills/catalog.json` is machine-validated taxonomy metadata and now drives installer canonical
directory discovery. The routing corpus checks the intended ownership model. Codex runtime routing
still uses skill metadata rather than consuming this catalog directly, so the catalog is not a full
runtime routing SSOT. Actual routing remains pending dogfood in a fresh Codex task.

## Framework Boundary

xLLM on Ascend NPU remains the complete primary path. vLLM-Ascend and SGLang support is limited to
the adapter or artifact scopes recorded in `skills/catalog.json`; PR12 does not claim interchangeable
end-to-end build, service, evaluation, profiling, and finalization support for those frameworks.

## Compatibility Boundary

All 19 baseline names remain canonical and resolve at their original paths. PR12 adds the lifecycle
and history-query canonical entries, for 21 total, and no aliases. Future aliases must resolve
directly to one canonical implementation and must not participate in implicit primary routing.
