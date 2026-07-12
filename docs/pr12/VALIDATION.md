# PR12 Validation Record

Date: 2026-07-12

## Results

| Check | Result |
|---|---|
| Baseline before PR12 | 138 passed |
| Phase 3 full tests | 148 passed |
| Pre-review full repository tests | 152 passed in 33.68s |
| Review-fix full repository tests | 159 passed in 36.68s |
| Catalog/schema validation | PASS; 21 canonical skills |
| Routing specification | 34 cases; each has one expected primary; all 20 public skills covered |
| Skill refresh | PASS; 21 canonical links rebuilt, 0 skipped |
| Broken symlink check | PASS; 0 broken links |
| Old-name compatibility smoke | PASS; 19/19 baseline names resolve |
| Canonical lifecycle command smoke | PASS; real CLI subprocess covers preflight through archive |
| Orphan `SKILL.md` detection | PASS; 0 orphan files |
| Catalog/install consistency | PASS; 21/21 canonical directories |
| README / README_zh / AGENTS consistency | PASS; all identify lifecycle and specialist routing boundaries |
| `git diff --check` | PASS |

Review-fix validation is complete. Fresh-task routing dogfood remains outside this task and pending.

## Pending Routing Dogfood

The routing corpus is a deterministic specification, not observed model-router accuracy. A real
routing dogfood remains **pending** and must run in a new Codex task after skill refresh so that the
new task receives the refreshed skill metadata. This Draft PR must not be marked ready based only on
the corpus.

## Conditional NPU Check

`npu-smi info` was available and healthy, but device 4 had a live process. No real NPU quick task
was started because this taxonomy PR provides no pinned model, binary, workload, or experiment spec.
Selecting those values here would expand scope and produce a non-comparable hardware result. The
required no-NPU synthetic lifecycle smoke passed.

## Claim Limits

- The routing corpus is an auditable deterministic specification, not a model-router accuracy score.
- `skills/catalog.json` is the taxonomy and installer canonical-discovery source. Codex runtime
  routing does not consume it directly, so it is not a complete runtime routing SSOT.
- Refresh proves filesystem discovery and policy presence only. Real routing behavior is pending a
  new Codex task.
- vLLM-Ascend and SGLang remain experimental adapter/artifact scopes.
