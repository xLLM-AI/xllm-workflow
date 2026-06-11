# xLLM AI Coding Workflow

Languages: [English](README.md) | [简体中文](README_zh.md)

Agent-ready workflows, prompts, schemas, and reference knowledge for NPU
large-model serving optimization on Ascend NPUs. First landing target:
[xLLM](https://github.com/jd-opensource/xllm); fair baselines:
[vLLM-Ascend](https://github.com/vllm-project/vllm-ascend) and SGLang NPU.

This is **not** the xLLM runtime or a benchmark archive — it is a reusable
AI coding workflow for engineers and agents that need fair evaluations,
profiling evidence, accuracy debugging, NPU code review, and reusable
optimization lessons. Requires Ascend 910B3/A3 NPU, CANN driver, and an
agent runtime (Codex, Claude Code, or opencode).

## Quick Start

### 1. Install The Skills

```bash
export AGENT_SKILL_DIR="${CODEX_HOME:-$HOME/.codex}/skills"   # Codex
# export AGENT_SKILL_DIR="$HOME/.claude/skills"               # Claude Code

mkdir -p "$AGENT_SKILL_DIR"
for skill_dir in skills/xllm-npu-*; do
  ln -sfn "$(pwd)/$skill_dir" "$AGENT_SKILL_DIR/$(basename "$skill_dir")"
done
```

### 2. Pick A Prompt

Copy a template from [`prompts/`](prompts/) and fill in model, hardware,
framework, workload, and target metrics.

| Prompt | Scenario |
|---|---|
| [`sota-loop`](prompts/xllm-npu-sota-loop-prompts.md) | End-to-end optimization, TPOT/decode gaps, MTP validation |
| [`eval-profiler`](prompts/xllm-npu-eval-profiler-prompts.md) | Service startup, evalscope, profiling, capacity/OOM |
| [`pr-fix`](prompts/xllm-npu-pr-fix-prompts.md) | PR regressions, review replies, rebase, build gates |
| [`op-migration`](prompts/xllm-npu-op-migration-prompts.md) | Operator migration, torch_npu/Triton-Ascend/AscendC |

### 3. Evidence Loop

Formal work follows `target → baseline → profiling → patch → accuracy → performance → record`.
See [AGENT.md](AGENT.md) for skill routing and [docs/workflow](docs/npu-ai-coding-standard-workflow.md) for phase details.

## Directory Overview

```text
1  AGENT.md            → Agent system prompt (constraints, skill routing, directory guide)
2  CLAUDE.md           → Claude Code redirect to AGENT.md
3  config.json         → Unified configuration SSOT (active / full_test / static)
4  prompts/            → Copy-ready task prompt templates (Chinese)
5  skills/             → 11 procedural agent skills (eval, profiler, benchmark, …)
6  reference/
     A  knowledge/     → Immutable domain rules (NPU specs in config.json static.npu_specs)
     B  code-style/    → C++/Python/NPU code style conventions
     C  io_specs/      → Artifact schemas (run manifest, perf, accuracy, profiling)
     D  pr_history/    → Model dossiers and PR history (queryable via scripts/query.py)
7  baseline/           → Performance acceptance criteria
8  scripts/            → Cross-skill shared deterministic scripts
9  humanize/           → Experience flywheel (validated troubleshooting lessons)
10 docs/               → NPU AI coding workflow documentation
11 tests/              → Repository hygiene and schema validators
12 code/               → External source mount (gitignored)
13 runs/               → Execution workspace (gitignored)
```

**`config.json`** is the single source of truth for all configuration. It has three blocks: `active` holds the current model, NPU, and serving parameters for the work at hand; `full_test` lists cross-model and cross-framework targets for comprehensive validation; `static` stores immutable hardware specs (NPU peak FLOPs, bandwidth, HBM). Skills and scripts read config.json instead of hardcoding values.

**`reference/`** is the static knowledge base — immutable domain rules that never change based on a single run. Skills query it for hardware limits, code style, artifact schemas, and historical optimization context.

**`humanize/`** is the experience flywheel — Agents write validated troubleshooting lessons here, making the workspace smarter over time. Concrete ledgers live under run roots; only durable lessons are promoted back.

**`scripts/`** is the deterministic engine — cross-skill shared automation scripts that LLMs must not modify. Changes to these scripts require human review.

**`skills/`** contains 11 procedural agent skills, each with a SKILL.md defining the execution workflow, evidence contracts, and local references. Agents load the smallest skill matching the task.

## Architecture

![xLLM AI Coding Workflow](docs/assets/xllm-ai-coding-workflow-en.png)

An evidence-driven loop: each optimization starts from a measurable target,
collects comparable data, makes one reviewable change, and leaves artifacts
for reproduction.

## Contribution Guidelines

- Turn reusable lessons into skills, references, schemas, or PR history entries.
- Keep public docs generic; model-specific lessons go in `reference/pr_history/`.
- Preserve failed attempts that explain future decisions.
- Do not commit local paths, private IPs, credentials, or non-public logs.
- Separate generic NPU evidence from framework-specific adapters.

## License

No license file yet. Add one before broad external reuse.