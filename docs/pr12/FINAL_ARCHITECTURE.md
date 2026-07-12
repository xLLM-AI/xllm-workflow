# PR12 Final Skill Architecture

## Public Routing Layers

```text
User intent
  |
  +-- experiment state ----------> xllm-experiment-lifecycle
  |                                  -> xllm-flow control plane
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

## Framework Boundary

xLLM on Ascend NPU remains the complete primary path. vLLM-Ascend and SGLang support is limited to
the adapter or artifact scopes recorded in `skills/catalog.json`; PR12 does not claim interchangeable
end-to-end build, service, evaluation, profiling, and finalization support for those frameworks.

## Compatibility Boundary

All 19 baseline names remain canonical and resolve at their original paths. PR12 adds one canonical
entry and no aliases. Future aliases must resolve directly to one canonical implementation and must
not participate in implicit primary routing.
