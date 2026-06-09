# xLLM AI Coding Workflow

Languages: [English](README.md) | [简体中文](README_zh.md)

Agent-ready workflows, prompts, schemas, and reference knowledge for large-model
serving optimization on Ascend NPUs.

The first supported landing target is
[xLLM](https://github.com/jd-opensource/xllm). The workflow also keeps
[vLLM-Ascend](https://github.com/vllm-project/vllm-ascend) and SGLang NPU in
scope as fair baselines, reusable references, and future adaptation targets.

This repository is not the xLLM runtime itself and it is not a benchmark result
archive. It is a reusable AI coding workflow for engineers and coding agents that
need to run fair evaluations, collect profiling evidence, debug accuracy
regressions, review NPU changes, and preserve lessons from optimization work.

## Who This Is For

Use this repository when you need to:

- optimize TTFT, TPOT, TPS, memory, or concurrency for NPU serving;
- compare xLLM with other OpenAI-compatible NPU serving frameworks fairly;
- debug garbled output, dataset score drops, GPU/NPU mismatches, crashes, OOM,
  graph failures, or HCCL issues;
- prepare or review xLLM NPU pull requests with reproducible evidence;
- migrate or prototype NPU operators after profiling proves the need;
- turn one-off optimization lessons into reusable agent skills and references.

This repository does not provide model weights, private benchmark datasets,
production logs, or guaranteed performance numbers for a specific environment.
All performance and accuracy conclusions must be reproduced in the user's own
hardware and software stack.

## Quick Start

### 1. Install The Skills

Symlinks are recommended so `git pull` updates the skills automatically:

```bash
export AGENT_SKILL_DIR="${CODEX_HOME:-$HOME/.codex}/skills"   # Codex example
# export AGENT_SKILL_DIR="$HOME/.claude/skills"               # Claude Code example

mkdir -p "$AGENT_SKILL_DIR"
for skill_dir in skills/xllm-npu-*; do
  ln -sfn "$(pwd)/$skill_dir" "$AGENT_SKILL_DIR/$(basename "$skill_dir")"
done
ln -sfn "$(pwd)/kernel-pilot" "$AGENT_SKILL_DIR/xllm-npu-kernel-pilot"
ln -sfn "$(pwd)/model-pr-optimization-history" "$AGENT_SKILL_DIR/model-pr-optimization-history"
```

If the target agent does not support symlinks, copy the needed skill
directories instead.

### 2. Pick A Task Prompt

Copy a prompt from [`prompts/`](prompts/) and fill in the model, hardware,
framework, workload, and target metrics.

| Prompt | Scenario |
|---|---|
| [`xllm-npu-sota-loop-prompts.md`](prompts/xllm-npu-sota-loop-prompts.md) | End-to-end optimization, TPOT targets, decode gaps, MTP validation |
| [`xllm-npu-eval-profiler-prompts.md`](prompts/xllm-npu-eval-profiler-prompts.md) | Service startup, evalscope, profiling, capacity, OOM analysis |
| [`xllm-npu-pr-fix-prompts.md`](prompts/xllm-npu-pr-fix-prompts.md) | PR regressions, review replies, rebase, build, UT gates |
| [`xllm-npu-op-migration-prompts.md`](prompts/xllm-npu-op-migration-prompts.md) | Operator migration, torch_npu, Triton-Ascend, AscendC, ATB |

### 3. Run Through The Evidence Loop

Formal optimization work should leave enough evidence for another contributor to
replay the conclusion:

```text
target -> baseline -> profiling -> patch -> accuracy -> performance -> record
```

Profiling runs explain bottlenecks. They do not replace non-profiling
before/after performance runs.

## What Is Included

| Area | Contents |
|---|---|
| [`skills/`](skills/) | Procedural agent skills for evaluation, profiling, benchmarking, accuracy debugging, incident triage, PR review, and operator migration |
| [`prompts/`](prompts/) | Copy-ready task prompts, currently written in Chinese for local engineering usability |
| [`references/`](references/) | Shared run manifest, performance, accuracy, profiling, NPU specs, and style contracts |
| [`docs/`](docs/) | General NPU AI coding workflow documentation |
| [`model-pr-optimization-history/`](model-pr-optimization-history/) | Queryable model and PR history for optimization decisions |
| [`humanize/`](humanize/) | Run-level ledger contract for recording decisions, review feedback, and lessons |
| [`kernel-pilot/`](kernel-pilot/) | Kernel-level experiment helper used after profiling justifies lower-level work |
| [`patches/`](patches/) | Minimal patches or migration notes, not full-file snapshots |

## Architecture

![xLLM AI Coding Workflow](docs/assets/xllm-ai-coding-workflow-en.png)

The repository is organized around an execution loop and reusable evidence
stores:

| Layer | Entry Point | Responsibility |
|---|---|---|
| Orchestrator | `xllm-npu-sota-loop` | Coordinates Research, Learn, Code, Review, Validate, and Record |
| Execution & Collection | `xllm-npu-eval-runner`, `xllm-npu-profiler`, `xllm-npu-incident-triage` | Starts services, runs evaluations, captures profiling, replays incidents, and collects raw artifacts |
| Analysis & Decision | benchmark / pipeline / capacity / compute / accuracy / code-review | Turns performance, accuracy, capacity, bubbles, hardware limits, and PR risks into verifiable conclusions |
| Supporting Knowledge | `model-pr-optimization-history`, `kernel-pilot`, `references/`, `humanize/` | Stores historical PRs, kernel experiments, artifact schemas, optimization ledgers, and lineage |

## Core Workflow

Many NPU serving optimizations fail because the evidence chain is broken:

- baseline runs have no warmup or run on contaminated devices;
- profiling traces are compared directly with non-profiling performance runs;
- MTP enablement is inferred only from evalscope accept rate;
- accuracy is judged from a few prompts without bad cases or A/B datasets;
- PR fixes do not preserve build, UT, accuracy, performance, and profiling
  artifacts.

This workflow addresses those issues with six recurring phases:

```text
Phase 0   Target and environment
Phase 0.5 Historical model knowledge
Phase 1   Fair baseline
Phase 2   Gap assessment
Phase 3   Evidence collection
Phase 4   Optimization plan
Phase 5   Research -> Learn -> Code -> Review -> Validate -> Record
Phase 6   Final record
```

The loop is inspired by
[PolyArch/humanize](https://github.com/PolyArch/humanize)'s RLCR discipline, but
this repository does not implement Humanize RLCR itself. In Humanize, RLCR means
Ralph-Loop with Codex Review: implementation work is reviewed independently and
fed back into the next iteration. Here, the xLLM NPU workflow expands that
review loop with benchmark, profiling, accuracy, and record-keeping gates.

See [`docs/npu-ai-coding-standard-workflow.md`](docs/npu-ai-coding-standard-workflow.md)
for the full workflow.

## Skills

| Task | Start With | Add When Needed |
|---|---|---|
| Run service, performance, or accuracy evaluation | [`xllm-npu-eval-runner`](skills/xllm-npu-eval-runner/SKILL.md) | Use `xllm-npu-benchmark` for fair cross-framework comparison |
| Optimize TPOT, TTFT, TPS, or throughput | [`xllm-npu-sota-loop`](skills/xllm-npu-sota-loop/SKILL.md) | Phase 3 should use profiler, pipeline, capacity, compute, or accuracy skills based on symptoms |
| Compare xLLM, vLLM-Ascend, and SGLang NPU | [`xllm-npu-benchmark`](skills/xllm-npu-benchmark/SKILL.md) | Keep failed candidates and startup commands |
| Explain profiling bottlenecks | [`xllm-npu-profiler`](skills/xllm-npu-profiler/SKILL.md) | Add pipeline analysis for decode bubbles or rank skew |
| Analyze prefill/decode boundaries | [`xllm-npu-pipeline-analysis`](skills/xllm-npu-pipeline-analysis/SKILL.md) | Add compute simulation for hardware lower bounds |
| Estimate memory and serving capacity | [`xllm-npu-capacity-planner`](skills/xllm-npu-capacity-planner/SKILL.md) | Add incident triage for crashes or OOM |
| Estimate FLOPs, MFU, and lower bounds | [`xllm-npu-compute-simulation`](skills/xllm-npu-compute-simulation/SKILL.md) | Use after workload and model shape are known |
| Debug garbled output or accuracy regressions | [`xllm-npu-accuracy-debug`](skills/xllm-npu-accuracy-debug/SKILL.md) | Use bisect when the introducing commit is unclear |
| Triage crash, OOM, graph, or HCCL incidents | [`xllm-npu-incident-triage`](skills/xllm-npu-incident-triage/SKILL.md) | Save replay commands and raw logs |
| Review NPU-related PRs | [`xllm-npu-code-review`](skills/xllm-npu-code-review/SKILL.md) | Also check the target repository's own agent rules |
| Migrate external or experimental operators | [`xllm-npu-op-migration`](skills/xllm-npu-op-migration/SKILL.md) | Use `kernel-pilot` only when a new kernel is justified |
| Query historical model work | [`model-pr-optimization-history`](model-pr-optimization-history/SKILL.md) | Update the dossier after reusable lessons are learned |
| Try kernel-level optimization | [`kernel-pilot`](kernel-pilot/SKILL.md) | First prove with profiling that the kernel is the bottleneck |

## Example Tasks

Run xLLM performance and accuracy:

```text
Use xllm-npu-eval-runner to start a Qwen3-32B xLLM service,
run evalscope with 5k input / 50 output / temperature=0,
and save manifest, metrics.json, report.md, and raw evalscope artifacts.
```

Compare multiple frameworks fairly:

```text
Compare xLLM, vLLM-Ascend, and SGLang NPU on A3 NPUs.
Use the same model, workload, sampling parameters, and SLA.
Tune each framework independently and output summary, candidates, and winning commands.
```

Diagnose a TPOT regression:

```text
Run warmed-up baseline/current performance tests.
Collect decode-focused profiling with xllm-npu-profiler.
Inspect the hostbound gap between replaceToken and the next GatherV2.
Produce a validated optimization candidate.
```

Run an end-to-end optimization loop:

```text
Use xllm-npu-sota-loop:
Phase 0 records the environment and target.
Phase 0.5 queries model-pr-optimization-history.
Phase 1 establishes a fair baseline.
Phase 3 collects profiling evidence.
Phase 5 applies one patch per round.
Each round reruns accuracy, performance, and profiling when needed.
The final result is recorded in humanize ledgers and model PR history.
```

## Evidence Contracts

Formal conclusions should include:

- run manifest;
- startup command, framework commit, and submodule status;
- model, tokenizer, dtype, hardware, workload, sampling parameters, and SLA;
- raw benchmark output and normalized summary;
- profiling report when profiling is used for diagnosis;
- accuracy report when correctness can be affected;
- final conclusion, known risks, failed attempts, and follow-up work.

Use these shared schemas when possible:

| Contract | Purpose |
|---|---|
| [`run-manifest-template.md`](references/run-manifest-template.md) | Commit, environment, model, startup command, workload, artifact paths |
| [`perf-artifact-schema.md`](references/perf-artifact-schema.md) | TTFT, TPOT, TPS, warmup, sampling parameters, server-side counters |
| [`accuracy-artifact-schema.md`](references/accuracy-artifact-schema.md) | Raw predictions, failed cases, scores, validation levels |
| [`profiling-artifact-schema.md`](references/profiling-artifact-schema.md) | msprof capture, five tables, timeline notes, inconclusive rules |

## Requirements

- Huawei Ascend 910B3 / A3 NPU, with compatibility notes for Ascend 910B / A2
- CANN / HDK driver compatible with the target framework
- At least one OpenAI-compatible serving framework: xLLM, vLLM-Ascend, or SGLang NPU
- evalscope and msprof / MindStudio profiling tools for formal evaluation and diagnosis
- Codex, Claude Code, opencode, or another agent runtime that can load local skills

## Repository Layout

```text
AGENTS.md                       Codex / opencode / generic agent project rules
CLAUDE.md                       Claude Code guardrails, synchronized with AGENTS.md
INSTRUCTIONS.md                 Short local orientation for agents and users
README.md                       Public English overview
docs/                           General NPU workflow documentation
skills/                         Core procedural agent skills
prompts/                        Copy-ready task prompts
references/                     Shared schemas, specs, and reusable rules
model-pr-optimization-history/   Historical model and PR knowledge
humanize/                       Run ledger contract
kernel-pilot/                   Kernel experiment helper
patches/                        Minimal patches or migration notes
tests/                          Repository hygiene and schema smoke tests
```

## Contribution Guidelines

- Turn reusable lessons into skills, references, schemas, prompt templates, or
  model history entries.
- Keep public entry documents generic; put model-specific lessons under
  `model-pr-optimization-history/` or skill `references/`.
- Preserve failed attempts when they explain a future decision.
- Do not commit local paths, private IPs, private dataset names, credentials,
  or non-public production logs.
- Do not present smoke results as formal performance or accuracy conclusions.
- When adding a new framework, separate the generic NPU evidence layer from the
  framework adapter layer.

## License

No license file has been added yet. Add a project license before advertising
this repository for broad external reuse.
