# AGENTS.md

Guidelines for Codex, opencode, Claude Code, and other coding agents working in
this repository.

This repository contains reusable AI coding workflows for NPU large-model serving
optimization. The first supported landing target is xLLM, but the evidence
model should stay portable to other OpenAI-compatible NPU serving frameworks
when their adapters and runbooks are added.

Claude Code should also read `CLAUDE.md`; keep both files aligned when changing
agent behavior.

## Repository Purpose

- Preserve repeatable NPU optimization workflows as skills, schemas, scripts,
  prompts, and model history.
- Keep benchmark, profiling, accuracy, capacity, and review evidence explicit.
- Separate generic workflow rules from model-specific or framework-specific
  lessons.
- Promote durable lessons into `model-pr-optimization-history/`, `references/`,
  `skills/*/references/`, or run-root `humanize/` ledgers.

## Core Rules

1. **Evidence before patch**: performance work needs a warmed-up baseline and
   profiling evidence before code changes. Accuracy work needs a stable
   reproducer.
2. **Fair comparisons only**: compare frameworks under the same model,
   tokenizer, dtype, hardware, workload, sampling parameters, and SLA. Tune each
   framework independently.
3. **Profiling is diagnostic**: profiling captures explain bottlenecks but do
   not replace non-profiling before/after performance runs.
4. **Review-gated evidence loop**: use
   `Research -> Learn -> Code -> Review -> Validate -> Record`. This is inspired
   by PolyArch/humanize's RLCR review discipline, but this repository does not
   implement Humanize RLCR itself.
5. **Small, verifiable changes**: make one meaningful change per validation
   round whenever practical.
6. **No private data**: do not commit private paths, host names, internal IPs,
   private datasets, credentials, or full production logs.
7. **Record reusable lessons**: failed attempts, review findings, performance
   conclusions, and accuracy lessons should be captured in durable references or
   run-root ledgers.

## Entry Points

| Entry | Use When |
|---|---|
| `README.md` / `README_zh.md` | Public overview and installation guidance |
| `docs/npu-ai-coding-standard-workflow.md` | Generic evidence-loop workflow |
| `prompts/` | Copy-ready task prompts for agents |
| `skills/*/SKILL.md` | Procedural task execution |
| `references/` | Shared schemas, specs, and reusable rules |
| `model-pr-optimization-history/` | Historical model and PR knowledge |
| `humanize/` | Ledger contract; concrete ledgers live under each run root |
| `kernel-pilot/` | Kernel-level experiments after profiling justifies them |

## Skill Routing

| Task | Start With |
|---|---|
| End-to-end optimization goal | `skills/xllm-npu-sota-loop/SKILL.md` |
| Launch service or collect evalscope artifacts | `skills/xllm-npu-eval-runner/SKILL.md` |
| Fair benchmark comparison | `skills/xllm-npu-benchmark/SKILL.md` |
| msprof / MindStudio profiling analysis | `skills/xllm-npu-profiler/SKILL.md` |
| Prefill/decode boundary, layer timing, or rank skew | `skills/xllm-npu-pipeline-analysis/SKILL.md` |
| Capacity, HBM, KV cache, concurrency, or OOM risk | `skills/xllm-npu-capacity-planner/SKILL.md` |
| FLOPs, MFU, or hardware lower-bound estimates | `skills/xllm-npu-compute-simulation/SKILL.md` |
| Garbled output, CEval drop, or GPU/NPU mismatch | `skills/xllm-npu-accuracy-debug/SKILL.md` |
| Crash, hang, HCCL, graph, or PagedAttention incident | `skills/xllm-npu-incident-triage/SKILL.md` |
| NPU code review before PR | `skills/xllm-npu-code-review/SKILL.md` |
| Operator migration | `skills/xllm-npu-op-migration/SKILL.md` |
| Kernel experiment | `kernel-pilot/SKILL.md` |
| Historical model knowledge | `model-pr-optimization-history/SKILL.md` |

## Evidence Loop

```text
Phase 0   Target and environment
Phase 0.5 Historical model knowledge
Phase 1   Fair baseline
Phase 2   Gap assessment
Phase 3   Profiling, capacity, pipeline, compute, or accuracy evidence
Phase 4   Optimization plan
Phase 5   Research -> Learn -> Code -> Review -> Validate -> Record
Phase 6   Final record and reusable lessons
```

Do not skip Phase 1 and Phase 3 for performance work. Do not claim success
without the raw commands, workload, metrics, and artifacts needed to reproduce
the result.

## Documentation Hygiene

- Keep public entry documents stable and generic.
- Put model-specific lessons under `model-pr-optimization-history/` or
  skill `references/`, not in the main README or generic workflow document.
- Remove temporary blog drafts, local environment notes, and stale roadmap text
  before opening a PR.
- Update README links when adding or removing documentation entry points.
- Keep `AGENTS.md` and `CLAUDE.md` conceptually aligned.
