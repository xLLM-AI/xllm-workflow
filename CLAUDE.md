# CLAUDE.md

Guidelines for Claude Code and other coding agents working in this repository.
These principles mirror the generic rules in `AGENTS.md`; keep both files in
sync when changing agent behavior.

## 1. Think Before Editing

- State assumptions when the task is ambiguous.
- If multiple interpretations change the implementation, ask before editing.
- If a simpler approach exists, say so before choosing a heavier path.
- Prefer the existing skill structure, artifact schema, and naming conventions.
- For trivial documentation fixes, make the small obvious edit and verify it.

## 2. Simplicity First

- Implement only what the user asked for and what the validation goal requires.
- Do not add abstractions, configuration, compatibility layers, or speculative
  features for a single-use need.
- If a change starts to sprawl, shrink it back to the smallest verifiable diff.

## 3. Evidence Before Patch

- Performance optimization requires a warmed-up baseline and profiling evidence
  before code changes.
- Accuracy fixes require a stable reproducer before broader evaluation.
- Profiling captures explain bottlenecks; they are not formal before/after
  performance results.
- Do not claim a gain without raw artifacts, metrics, and the exact workload.

## 4. Keep Changes Surgical

- Touch only files needed for the request.
- Do not rewrite skill bodies into long essays. Keep `SKILL.md` procedural and
  move detailed material into `references/` when needed.
- Do not delete failed attempts or historical lessons; convert them into
  reusable notes.
- Do not add local paths, private host names, internal IPs, private datasets, or
  secrets to committed files.

## 5. Use the Right Entry Point

- End-to-end performance goal: `xllm-npu-sota-loop`.
- Service launch or evalscope collection: `xllm-npu-eval-runner`.
- Fair cross-framework comparison: `xllm-npu-benchmark`.
- msprof / MindStudio analysis: `xllm-npu-profiler`.
- Decode bubble or rank skew: `xllm-npu-pipeline-analysis`.
- Garbled output or dataset score drop: `xllm-npu-accuracy-debug`.
- Crash, OOM, graph, HCCL, or PagedAttention failure: `xllm-npu-incident-triage`.
- NPU code review before PR: `xllm-npu-code-review`.
- Operator migration: `xllm-npu-op-migration`, then `kernel-pilot` only when
  profiling justifies kernel work.

## 6. Validate and Record

- Run repository tests after changing schemas, scripts, or skill structure.
- For documentation-only edits, at least run markdown-sensitive hygiene checks
  when available.
- Update README / README.zh / AGENTS.md together when changing public workflow
  concepts.
- End every optimization or bug-fix loop by recording reusable lessons in a
  ledger, reference, or model PR history.
