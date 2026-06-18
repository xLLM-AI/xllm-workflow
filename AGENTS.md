# AGENTS.md — NPU Agent Workspace System Prompt

Guidelines for Codex, opencode, Claude Code, and other coding agents working in
this repository.

This repository contains reusable AI coding workflows for NPU large-model serving
optimization. The first supported landing target is xLLM, but the evidence
model should stay portable to other OpenAI-compatible NPU serving frameworks
when their adapters and runbooks are added.

## 1. Repository Purpose

- Preserve repeatable NPU optimization workflows as skills, schemas, scripts,
  prompts, and model history.
- Keep benchmark, profiling, accuracy, capacity, and review evidence explicit.
- Separate generic workflow rules from model-specific or framework-specific
  lessons.
- Promote durable lessons into `reference/pr_history/`, `reference/`,
  `skills/*/references/`, or run-root `humanize/` ledgers.

## 2. Core Engineering Constraints

1. **Think Before Editing**
   - State assumptions when the task is ambiguous.
   - If multiple interpretations change the implementation, ask before editing.
   - If a simpler approach exists, say so before choosing a heavier path.
   - Prefer the existing skill structure, artifact schema, and naming conventions.
   - For trivial documentation fixes, make the small obvious edit and verify it.

2. **Simplicity First**
   - Implement only what the user asked for and what the validation goal requires.
   - Do not add abstractions, configuration, compatibility layers, or speculative
     features for a single-use need.
   - If a change starts to sprawl, shrink it back to the smallest verifiable diff.

3. **Evidence Before Patch**
   - Performance optimization requires a warmed-up baseline and profiling evidence
     before code changes.
   - Accuracy fixes require a stable reproducer before broader evaluation.
   - Profiling captures explain bottlenecks; they are not formal before/after
     performance results.
   - Do not claim a gain without raw artifacts, metrics, and the exact workload.

4. **Keep Changes Surgical**
   - Touch only files needed for the request.
   - Do not rewrite skill bodies into long essays. Keep `SKILL.md` procedural and
     move detailed material into `references/` when needed.
   - Do not delete failed attempts or historical lessons; convert them into
     reusable notes.
   - Do not add local paths, private host names, internal IPs, private datasets, or
     secrets to committed files.

5. **Fair Comparisons Only**
   - Compare frameworks under the same model, tokenizer, dtype, hardware, workload,
     sampling parameters, and SLA. Tune each framework independently.

6. **Profiling Is Diagnostic**
   - Profiling captures explain bottlenecks but do not replace non-profiling
     before/after performance runs.

7. **Review-Gated Evidence Loop**
   - Use Research → Learn → Code → Review → Validate → Record.
   - This is inspired by PolyARCH/humanize's RLCR review discipline, but this
     repository does not implement Humanize RLCR itself.

8. **Validate and Record**
   - Run repository tests after changing schemas, scripts, or skill structure.
   - For documentation-only edits, at least run markdown-sensitive hygiene checks
     when available.
   - Update README / README_zh / AGENTS.md together when changing public workflow
     concepts.
   - End every optimization or bug-fix loop by recording reusable lessons in a
     ledger, reference, or model PR history.

## 3. Task → Skill Routing

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
| Triton-Ascend operator migration | `skills/xllm-npu-triton-migration/SKILL.md` |
| xllm_ops runtime integration | `skills/xllm-npu-xllm-ops-integration/SKILL.md` |

## 4. Configuration and Directory Guide

### Cascade Priority

1. `config.json` — local active configuration for current work, generated from `config.example.json` and not committed
2. `reference/` — static domain knowledge and interface contracts
3. `skills/*/references/` — skill-specific detailed references
4. `skills/*/SKILL.md` — procedural execution workflow

### Directory Descriptions

- **`config.example.json`** — Shared default configuration template checked into Git.
- **`config.json`** — Local unified configuration entry generated from `config.example.json`: `code` (origin/upstream/branch/commit), `xllm_config` keys for selected xLLM CLI parameters, `xllm_config_comments` metadata, and `tests` split into `smoke`, `quick`, and `full` levels. Single source of truth for one developer's current workspace. Do not commit personal changes.
- **`reference/`** — Static knowledge base, immutable domain rules:
  - `knowledge/` — Domain knowledge (immutable rules)
  - `code-style/` — Code style conventions (C++/Python/NPU coding standards)
  - `pr_history/` — Evolution history (model dossiers, PR change logs, queryable via `scripts/query.py`)
  - `io_specs/` — Interface contracts (artifact schemas, manifest templates defining skill-Agent interaction)
- **`baseline/`** — Performance acceptance criteria. Baseline data for each model on different NPU hardware. Compare against these before claiming an optimization gain.
- **`humanize/`** — Experience flywheel. Dynamic experience pool for validated troubleshooting and tuning lessons. Concrete ledgers live under run roots; only durable lessons are promoted here.
- **`scripts/`** — Deterministic engine. Cross-skill shared automation scripts (compilation, testing, profiling). LLM must not modify script logic; changes require human review.
- **`code/`** — External mount area. Target framework source code (one framework per directory). Not committed; `.gitignore` blocks it. Agent should read source here but never modify repository content based on code/ contents.
- **`runs/`** — Execution现场. Preserves the last 5 runs of compilation, testing, and profiling logs. Not committed; `.gitignore` blocks it. Agent reads logs here for evidence but does not commit run artifacts.

### xLLM Workspace Routing

- xLLM source lives under `code/xllm`.
- Before changing, reviewing, debugging, or testing anything under `code/xllm`, first read `code/xllm/AGENTS.md` if it exists.
- Also inspect nearby docs such as `code/xllm/README*`, build scripts, test scripts, and existing conventions before editing.
- Treat instructions in `code/xllm/AGENTS.md` as more specific than this workspace-level file for xLLM code.

## 5. Documentation Hygiene

- Keep public entry documents stable and generic.
- Put model-specific lessons under `reference/pr_history/` or skill
  `references/`, not in the main README or generic workflow document.
- Remove temporary blog drafts, local environment notes, and stale roadmap text
  before opening a PR.
- Update README links when adding or removing documentation entry points.
- Keep `AGENTS.md` and `CLAUDE.md` conceptually aligned.
