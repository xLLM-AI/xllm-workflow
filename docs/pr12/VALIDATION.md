# PR12 Validation Record

Date: 2026-07-12

## Results

| Check | Result |
|---|---|
| Baseline before PR12 | 138 passed |
| Phase 3 full tests | 148 passed |
| Final full repository tests | 152 passed in 33.68s |
| Catalog/schema validation | PASS; 20 canonical skills |
| Routing evaluation | PASS; 32/32 cases have one expected primary; 0 missing lifecycle routes |
| Skill refresh | PASS; 20 links rebuilt, 0 skipped |
| Broken symlink check | PASS; none found |
| Old-name compatibility smoke | PASS; 19/19 baseline names resolve |
| Canonical lifecycle entry smoke | PASS; installed `xllm-experiment-lifecycle/SKILL.md` resolves |
| Synthetic lifecycle smoke | PASS; create/finalize/archive and tamper rejection, 3 tests |
| README / README_zh / AGENTS consistency | PASS; all identify lifecycle and specialist routing boundaries |
| `git diff --check` | PASS |

The same results are recorded in the Phase 6 Issue comment and Draft PR.

## Conditional NPU Check

`npu-smi info` was available and healthy, but device 4 had a live process. No real NPU quick task
was started because this taxonomy PR provides no pinned model, binary, workload, or experiment spec.
Selecting those values here would expand scope and produce a non-comparable hardware result. The
required no-NPU synthetic lifecycle smoke passed.

## Claim Limits

- The routing corpus is an auditable deterministic specification, not a model-router accuracy score.
- The refresh proves filesystem discovery and policy presence; a new Codex task is required to
  observe refreshed implicit skill injection behavior.
- vLLM-Ascend and SGLang remain experimental adapter/artifact scopes.
