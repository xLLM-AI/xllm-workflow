# Patches

This directory is reserved for small, reviewable patch artifacts.

Do not store full source-file snapshots here. They become stale quickly and can
be mistaken for code that is safe to copy into the current framework tree.

For historical optimizations, prefer:

- a minimal `.patch` or `.diff` generated from the relevant commit;
- a reusable reference or model history entry;
- a model dossier entry under `model-pr-optimization-history/`;
- a lineage entry under `humanize/`.

The former Qwen3.5 MTP transpose full-file snapshots were removed. Use
`model-pr-optimization-history/xllm/qwen35-mtp.md` as the source of truth for
that case.
