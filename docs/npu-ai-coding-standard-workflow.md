# NPU AI Coding Standard Workflow

This document defines the common workflow used by this repository for NPU
large-model serving optimization. The workflow is intentionally evidence-driven:
each optimization should start from a measurable target, collect comparable
data, make one reviewable change at a time, and leave enough artifacts for
another contributor to reproduce the conclusion.

The current skills are named around xLLM because xLLM is the first supported
landing target. The workflow itself should remain portable to other
OpenAI-compatible NPU serving frameworks when their launch commands, metrics,
logs, and profiling adapters are added.

## Principles

- Keep benchmark, profiling, accuracy, and capacity evidence separate.
- Compare frameworks only under the same model, tokenizer, dtype, hardware,
  workload, sampling parameters, and SLA.
- Treat profiling as diagnostic evidence, not as the final performance number.
- Apply one meaningful patch per validation round whenever practical.
- Record failed attempts as well as successful optimizations.
- Do not commit private paths, private hosts, credentials, non-public logs, or
  temporary environment notes.

## Evidence Loop

```text
target -> baseline -> profiling -> patch -> accuracy -> performance -> record
```

The loop is designed to prevent common mistakes:

- optimizing without a stable baseline;
- comparing a tuned framework against an untuned framework;
- using profiling runs as formal throughput measurements;
- declaring success without accuracy checks;
- losing the command, commit, environment, or artifact paths needed to replay
  the result.

## Phase 0: Target And Environment

Record the target before running experiments:

- model, tokenizer, precision, quantization, and model-specific options;
- NPU type, device count, CANN, driver, torch_npu or framework runtime versions;
- framework name and commit;
- container or runtime image;
- launch command and visible devices;
- workload, sampling parameters, SLA, and artifact root.

Use `reference/io_specs/run-manifest-template.md` as the common manifest shape.

## Phase 1: Fair Baseline

Establish a warmed-up baseline before changing code or tuning parameters.

Required rules:

- use the same model, tokenizer, dtype, hardware, workload, sampling, and SLA;
- tune each framework independently before comparing results;
- preserve failed candidates and their failure reasons;
- save startup commands, raw benchmark output, NPU snapshots, and normalized
  summaries.

Relevant skills:

- `skills/xllm-npu-eval-runner/SKILL.md`
- `skills/xllm-npu-benchmark/SKILL.md`

## Phase 2: Gap Assessment

Use the baseline to decide whether optimization is needed.

```text
gap = (reference_throughput - target_throughput) / reference_throughput
```

If the target already meets the goal, record the configuration and stop. If the
gap is meaningful, move to profiling, capacity, pipeline, or accuracy analysis
based on the observed symptom.

## Phase 3: Evidence Collection

Collect the evidence needed to explain the gap.

Common evidence types:

- profiling: kernel, communication, fusion, dispatch, and memory evidence;
- pipeline: prefill/decode split, layer timing, rank skew, and decode bubbles;
- capacity: HBM, KV cache, concurrency, fragmentation, and OOM risk;
- compute: FLOPs, MFU, shape assumptions, and hardware lower bounds;
- accuracy: stable bad cases, A/B outputs, dataset subsets, and full benchmark
  results when needed.

Relevant skills:

- `skills/xllm-npu-profiler/SKILL.md`
- `skills/xllm-npu-pipeline-analysis/SKILL.md`
- `skills/xllm-npu-capacity-planner/SKILL.md`
- `skills/xllm-npu-compute-simulation/SKILL.md`
- `skills/xllm-npu-accuracy-debug/SKILL.md`
- `skills/xllm-npu-incident-triage/SKILL.md`

## Phase 4: Optimization Plan

Derive the optimization plan from evidence, not from intuition alone.

A useful plan should include:

- the suspected root cause;
- the source paths or framework components involved;
- the proposed change;
- expected performance or reliability impact;
- accuracy, graph-mode, memory, communication, and compatibility risks;
- the validation commands and artifacts that will prove or disprove the change.

For operator work, choose the narrowest existing entry point: use
`skills/xllm-npu-triton-migration/SKILL.md` for Triton-Ascend AOT migration and
`skills/xllm-npu-xllm-ops-integration/SKILL.md` when an existing xllm_ops custom
op must be wired into xLLM runtime. Only proceed to kernel-level work after
profiling shows that a kernel-level path is the right next step.

## Phase 5: Review-Gated Iteration

Each optimization round follows a review-gated evidence loop inspired by
PolyArch/humanize's RLCR discipline. Humanize RLCR means Ralph-Loop with Codex
Review; this repository does not implement that plugin loop directly. Instead,
it adapts the same independent-review idea to xLLM NPU optimization:

```text
Research -> Learn -> Code -> Review -> Validate -> Record
```

- Research: read benchmark, profiling, capacity, compute, and accuracy evidence.
- Learn: check relevant model optimization history and previous failed attempts.
- Code: make one reviewable change.
- Review: apply NPU-specific code review rules before pushing.
- Validate: run the narrowest sufficient build, test, accuracy, performance, and
  profiling checks.
- Record: update the run artifacts and long-term knowledge stores.

Relevant skills:

- `skills/xllm-npu-sota-loop/SKILL.md`
- `skills/xllm-npu-code-review/SKILL.md`
- `reference/pr_history/SKILL.md`

## Phase 6: Record

Every completed round should leave enough context for replay.

Recommended artifacts:

- run manifest;
- benchmark summary and raw output;
- profiling report and timeline notes;
- accuracy report and failed cases;
- capacity or compute estimates when used;
- patch summary and validation result;
- final conclusion with known risks and follow-up work.

Use the schemas in `reference/io_specs/` for common artifact formats:

- `reference/io_specs/perf-artifact-schema.md`
- `reference/io_specs/profiling-artifact-schema.md`
- `reference/io_specs/accuracy-artifact-schema.md`
- `reference/io_specs/run-manifest-template.md`

## Contribution Guidance

When adding new workflow knowledge:

- prefer reusable skills, references, schemas, and scripts over one-off notes;
- keep framework-specific launch details out of generic workflow text when
  possible;
- keep examples sanitized and reproducible;
- remove temporary blog drafts, environment notes, and private run details before
  opening a PR;
- update README links when adding or removing documentation entry points.
