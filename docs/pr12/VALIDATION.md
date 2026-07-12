# PR12 Validation Record

Date: 2026-07-12

## Results

| Check | Result |
|---|---|
| Baseline before PR12 | 138 passed |
| Phase 3 full tests | 148 passed |
| Pre-review full repository tests | 152 passed in 33.68s |
| Review-fix full repository tests | 159 passed in 36.68s |
| Fresh-task dogfood full repository tests | 159 passed in 36.87s |
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
| Fresh-task observed routing | PASS; 14/14 primary matches (100%) |
| Lifecycle create/resume/finalize dogfood | PASS; 3/3 route to `xllm-experiment-lifecycle` |
| Internal skill implicit primary | PASS; 0 occurrences |
| Explicit `$ssh-remote-exec` route | PASS; 1/1 selected, no remote command executed |

Review-fix validation and fresh-task routing dogfood are complete. PR #13 remains Draft for human
review and has not been merged or marked Ready for Review.

## Fresh-Task Routing Dogfood

The routing corpus remains a deterministic specification rather than a model-router harness. A new
Codex task refreshed the canonical skill links, then ran 14 isolated routing-only probes before
reading the specification's `expected_primary` values. All 14 observed primaries matched. Ordinary
prompts never selected the internal `ssh-remote-exec` skill, while explicit `$ssh-remote-exec`
selected it without executing a remote command. See `docs/pr12/ROUTING_DOGFOOD.md` for the sealed
observations and per-case comparison.

## Conditional NPU Check

`npu-smi info` was available and healthy, but device 4 had a live process. No real NPU quick task
was started because this taxonomy PR provides no pinned model, binary, workload, or experiment spec.
Selecting those values here would expand scope and produce a non-comparable hardware result. The
required no-NPU synthetic lifecycle smoke passed.

## Claim Limits

- The routing corpus is an auditable deterministic specification, not a model-router accuracy score.
- `skills/catalog.json` is the taxonomy and installer canonical-discovery source. Codex runtime
  routing does not consume it directly, so it is not a complete runtime routing SSOT.
- Refresh alone proves filesystem discovery and policy presence; the separate fresh-task dogfood
  now provides 14 observed routing selections, without turning that bounded sample into a general
  probabilistic accuracy claim.
- vLLM-Ascend and SGLang remain experimental adapter/artifact scopes.
