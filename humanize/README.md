# Humanize Ledgers

This directory defines the ledger contract for optimization runs.

Do not keep root-level run records here. Concrete attempt ledgers, optimization
ledgers, idea-source ledgers, and lineage files belong under each run root:

```text
<run-root>/humanize/
  attempt-ledger.md
  optimization-ledger.md
  source-idea-ledger.md
  lineage.jsonl
```

Promote only durable lessons back into this repository:

- model-specific risks and wins -> `model-pr-optimization-history/`
- profiling lessons -> profiler references or model history
- reusable artifact fields -> `references/`
- repeatable workflows -> `skills/`

This prevents stale local experiment paths from becoming global guidance while
still preserving the evidence-loop record for each run.
