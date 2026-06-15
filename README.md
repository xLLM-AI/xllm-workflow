# xLLM AI Coding Workflow

Languages: [English](README.md) | [简体中文](README_zh.md)

Agent-ready workflows, prompts, schemas, and reference knowledge for NPU
large-model serving optimization on Ascend NPUs. First landing target:
[xLLM](https://github.com/jd-opensource/xllm); fair baselines:
[vLLM-Ascend](https://github.com/vllm-project/vllm-ascend) and SGLang NPU.

**What this repository handles:**

1. **Feature design & development** — Design new NPU serving features, write code, and validate through review-gated evidence loops.
2. **Issue diagnosis & fix** — Locate accuracy regressions, crashes, OOM, graph failures, or HCCL issues; produce reproducible evidence and validated patches.
3. **Performance optimization** — Establish fair baselines, collect profiling evidence, identify bottlenecks, and iterate toward TPOT/TTFT/TPS targets with measurable gains.

## 1 Quick Start

### A. Initialize xLLM And Skills

Mode 1 starts the code agent from this repository root. The script clones or
reuses `code/xllm`, links this project's `skills/*` into `.agents/skills`, and
links xLLM repository skills into the same generated directory.

```bash
python scripts/init_xllm_workspace.py
```

Mode 2 starts the code agent from `code/xllm`. The same script installs this
project's `skills/*` into the selected agent skills directory, while xLLM keeps
using its own repository-local skills.

```bash
python scripts/init_xllm_workspace.py --mode xllm --agent codex
```

The initialization script creates local `config.json` from
`config.example.json` when needed. It then reads xLLM repository settings from
`config.json`; if they are missing, it asks for the Git URL and branch or
commit, writes them back to local `config.json`, and clones `code/xllm` when the
directory is missing or empty.

### B. Start The Code Agent

For Mode 1, start the code agent from this repository root so it can load
`AGENTS.md` and the generated `.agents/skills` directory.

```bash
codex
```

For Mode 2, start the code agent from the xLLM repository.

```bash
cd code/xllm
codex
```

### C. Pick A Prompt

Copy a template from [`prompts/`](prompts/) and fill in model, hardware,
framework, workload, and target metrics.

| Prompt | Scenario |
|---|---|
| [`sota-loop`](prompts/xllm-npu-sota-loop-prompts.md) | End-to-end optimization, TPOT/decode gaps, MTP validation |
| [`eval-profiler`](prompts/xllm-npu-eval-profiler-prompts.md) | Service startup, evalscope, profiling, capacity/OOM |
| [`pr-fix`](prompts/xllm-npu-pr-fix-prompts.md) | PR regressions, review replies, rebase, build gates |
| [`op-migration`](prompts/xllm-npu-op-migration-prompts.md) | Operator migration, torch_npu/Triton-Ascend/AscendC, xllm_ops runtime integration |

### D. Execute Workflow

Formal work follows `target → baseline → profiling → patch → accuracy → performance → record`.
See [AGENTS.md](AGENTS.md) for skill routing and [docs/workflow](docs/npu-ai-coding-standard-workflow.md) for phase details.

## 2 Directory Overview

```text
AGENTS.md           → Agent system prompt (constraints, skill routing, directory guide)
CLAUDE.md           → Claude Code redirect to AGENTS.md
config.example.json → Shared default configuration template
config.json         → Local configuration SSOT, generated and gitignored
prompts/            → Copy-ready task prompt templates (Chinese)
skills/             → 13 procedural agent skills (eval, profiler, benchmark, operator migration, …)
reference/
   knowledge/    → Immutable domain rules (NPU specs in config.json xllm.hardware.npu_specs)
   code-style/   → C++/Python/NPU code style conventions
   io_specs/     → Artifact schemas (run manifest, perf, accuracy, profiling)
   pr_history/   → Model dossiers and PR history (queryable via scripts/query.py)
baseline/           → Performance acceptance criteria
scripts/            → Cross-skill shared deterministic scripts
humanize/           → Experience flywheel (validated troubleshooting lessons)
docs/               → NPU AI coding workflow documentation
tests/              → Repository hygiene and schema validators
code/               → External source mount (gitignored)
runs/               → Execution workspace (gitignored)
```

**`config.example.json`** is the shared default template. **`config.json`** is the local single source of truth for one developer's workspace and is intentionally gitignored. Its top-level order is `code` (origin/upstream/branch/commit), `xllm` (model, draft model, feature flags, and launch args aligned with xLLM startup parameters), `dev_test` (small input/output/concurrency/dtype/script settings), and `full_test` (comprehensive validation matrix). Skills and scripts read local config.json instead of hardcoding values.

**`reference/`** is the static knowledge base — immutable domain rules that never change based on a single run. Skills query it for hardware limits, code style, artifact schemas, and historical optimization context.

**`humanize/`** is the experience flywheel — Agents write validated troubleshooting lessons here, making the workspace smarter over time. Concrete ledgers live under run roots; only durable lessons are promoted back.

**`scripts/`** is the deterministic engine — cross-skill shared automation scripts that LLMs must not modify. Changes to these scripts require human review.

**`skills/`** contains 13 procedural agent skills, each with a SKILL.md defining the execution workflow, evidence contracts, and local references. Mode 1 links them into generated `.agents/skills`; Mode 2 links them into the selected agent skills directory.

## 3 Typical Workflow

![xLLM AI Coding Workflow](docs/assets/xllm-ai-coding-workflow-en.png)

An evidence-driven loop: each optimization starts from a measurable target,
collects comparable data, makes one reviewable change, and leaves artifacts
for reproduction.

## 4 Contribution Guidelines

1. **Deterministic capabilities go into scripts** — Any automatable deterministic logic (compile, evaluate, profiling collection) should be locked into `scripts/`; LLM must not modify script logic.
2. **Reusable workflows become Skills** — Repeated standard workflows (benchmark comparison, PR review) should be encapsulated as `skills/` Skills, not scattered notes.
3. **Pitfall lessons & best practices go into humanize** — Validated troubleshooting lessons, tuning insights, and recurring pitfalls belong in `humanize/`, making the workspace smarter over time.
4. **Avoid duplication** — Configuration, specs, and prompts must not appear in multiple places; keep one source and reference it (SSOT).
5. **Do not commit local paths, private IPs, credentials, or non-public logs.**

## 5 License

No license file yet. Add one before broad external reuse.
