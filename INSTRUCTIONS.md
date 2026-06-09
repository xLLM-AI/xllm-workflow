# Quick Start

This repository provides reusable workflows for NPU large-model serving
optimization. It is intended for engineers and agents that need to run fair
benchmarks, collect profiling evidence, debug accuracy issues, review NPU code,
and preserve reusable optimization lessons.

The current skills are named around xLLM because xLLM is the first supported
landing target. Keep generic workflow rules separate from framework-specific or
model-specific lessons.

## Start Here

1. Read `README.md` or `README_zh.md` for the public overview.
2. Read `AGENTS.md` before using this repository from Codex, opencode, Claude
   Code, or another coding agent.
3. Read `docs/npu-ai-coding-standard-workflow.md` for the standard evidence loop.
4. Choose a prompt from `prompts/` if you want a copy-ready task request.
5. Load the smallest skill that matches the task.

## Common Tasks

| Task | Entry Point |
|---|---|
| End-to-end optimization goal | `skills/xllm-npu-sota-loop/SKILL.md` |
| Launch service or collect evalscope artifacts | `skills/xllm-npu-eval-runner/SKILL.md` |
| Fair benchmark comparison | `skills/xllm-npu-benchmark/SKILL.md` |
| Profiling and bottleneck analysis | `skills/xllm-npu-profiler/SKILL.md` |
| Decode bubble or rank-skew analysis | `skills/xllm-npu-pipeline-analysis/SKILL.md` |
| Capacity or OOM analysis | `skills/xllm-npu-capacity-planner/SKILL.md` |
| Accuracy regression debugging | `skills/xllm-npu-accuracy-debug/SKILL.md` |
| Incident triage | `skills/xllm-npu-incident-triage/SKILL.md` |
| NPU code review | `skills/xllm-npu-code-review/SKILL.md` |
| Operator migration | `skills/xllm-npu-op-migration/SKILL.md` |
| Kernel-level experiment | `kernel-pilot/SKILL.md` |
| Historical model knowledge | `model-pr-optimization-history/SKILL.md` |

## Evidence Loop

```text
target -> baseline -> profiling -> patch -> accuracy -> performance -> record
```

Use the six-phase workflow:

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

## Artifact Expectations

Formal conclusions should include:

- run manifest;
- startup command and framework commit;
- model, tokenizer, dtype, hardware, workload, sampling parameters, and SLA;
- raw benchmark output and normalized summary;
- profiling report when used for diagnosis;
- accuracy report when correctness can be affected;
- final conclusion, known risks, and follow-up work.

Use these shared schemas when possible:

- `references/run-manifest-template.md`
- `references/perf-artifact-schema.md`
- `references/profiling-artifact-schema.md`
- `references/accuracy-artifact-schema.md`

## Repository Layout

```text
AGENTS.md                       Agent project rules
CLAUDE.md                       Claude Code guardrails
README.md                       Default English overview
README_zh.md                    Chinese overview
docs/                           Generic workflow documentation
skills/                         Procedural agent skills
prompts/                        Copy-ready task prompts
references/                     Shared schemas and reusable rules
model-pr-optimization-history/   Historical model and PR knowledge
humanize/                       Run ledger contract
kernel-pilot/                   Kernel experiment helper
patches/                        Small patch artifacts only
tests/                          Repository hygiene and smoke tests
```

## Hygiene Rules

- Do not commit private paths, internal IPs, credentials, private datasets, or
  production logs.
- Do not put temporary environment notes or blog drafts into public entry docs.
- Put model-specific history under `model-pr-optimization-history/` or skill
  references.
- Keep README links current when adding or removing documentation files.
