# PR12 Routing Matrix

This Phase 1 matrix defines desired primary ownership before any structural change. It is an
auditable specification backed by `tests/routing/cases.yaml`, not a measured model accuracy claim.

| Intent | Expected primary | Allowed followups | Forbidden primary |
|---|---|---|---|
| Create/resume/finalize/archive/evidence lifecycle | Missing public lifecycle route | build/eval/report as required | build, server, report or SSH as lifecycle owner |
| Open-ended performance optimization with code iteration | `xllm-npu-sota-loop` | benchmark, profiler, pipeline, capacity, compute, eval, review | perf runner or build gate |
| Existing-result fairness, SLA or publishable comparison | `xllm-npu-benchmark` | eval for missing measurements, report writer | raw perf runner |
| Mixed performance and accuracy suite | `xllm-npu-eval-runner` | server, perf, accuracy, report | benchmark as executor |
| One explicit performance workload | `xllm-npu-perf-runner` | none unless service is absent | batch, benchmark |
| One explicit accuracy workload | `xllm-npu-accuracy-runner` | none unless service is absent | accuracy-debug |
| Multi-model/config or repeated campaign | `xllm-npu-batch-perf` | server, perf, report | benchmark as executor |
| Profile capture or generic five-table analysis | `xllm-npu-profiler` | pipeline when deeper mapping is needed | pipeline as collector |
| Existing-trace stage/layer/rank/bubble analysis | `xllm-npu-pipeline-analysis` | profiler for missing artifacts | perf/eval runner |
| Stable correctness regression | `xllm-npu-accuracy-debug` | accuracy runner | accuracy runner as primary |
| Runtime/build incident | `xllm-npu-incident-triage` | build gate or profiler | server/build gate as diagnosis owner |
| Healthy explicit build/provenance maintenance | `xllm-npu-build-gate` | none | incident triage |
| Explicit service lifecycle maintenance | `xllm-npu-server-manager` | none | eval runner |
| Capacity, compute, review or operator work | Corresponding specialist | evidence-producing runners as needed | unrelated low-level gate |
| Render a completed run with a supplied template | `xllm-npu-report-writer` | none | eval runner |

The matrix deliberately preserves direct runner, build, service and report intents. Phase 3/5 may
change visibility only when routing cases show that an independent intent has no value.
