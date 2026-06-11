# humanize/ — Experience Flywheel

This directory is the dynamic experience pool. Agents accumulate troubleshooting
and tuning lessons here, making the workspace "smarter with every use."

## Purpose

- Preserve validated optimization conclusions, troubleshooting experience, and recurring pitfalls
- Provide reference for future Agents executing similar tasks
- Complement static knowledge in `reference/` with run-proven lessons

## Write-back Rules

- Only write **validated lessons** (not guesses, not hypotheses)
- Each lesson must include: scenario, root cause, solution, verification method
- Concrete ledger files (attempt-ledger, optimization-ledger, source-idea-ledger, lineage.jsonl)
  are generated under each run root (`runs/`), not here
- Only lessons with durable value are promoted back into this directory

## Ledger Contract

Concrete ledgers live under each run root:

```text
<run-root>/humanize/
  attempt-ledger.md
  optimization-ledger.md
  source-idea-ledger.md
  lineage.jsonl
```

Promote durable lessons into the repository:

- model-specific risks and wins → `reference/pr_history/`
- profiling lessons → skill references or `reference/pr_history/`
- reusable artifact fields → `reference/io_specs/`
- repeatable workflows → `skills/`

This prevents stale local experiment paths from becoming global guidance while
still preserving the evidence-loop record for each run.

## Current State

(Directory starts empty. Content fills organically as Agents accumulate real
troubleshooting and tuning experience.)