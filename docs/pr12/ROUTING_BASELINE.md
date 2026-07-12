# PR12 Routing Baseline

## Method

The repository has no deterministic model-router harness. Phase 1 therefore records a fixed
30-plus prompt corpus as an auditable routing specification. Tests validate coverage, references,
negative routes and explicit missing-route gaps. They do not claim a probabilistic routing score.

## Baseline Summary

- Cases: 32.
- Cases with multiple current primary candidates: at least 20.
- Missing public lifecycle route cases: create, resume, finalize, archive and evidence validation.
- Current skills: 19.
- Baseline repository tests before changes: 138 passed.

## Ambiguity Clusters

| Cluster | Current candidates | Evidence-backed desired owner |
|---|---|---|
| Experiment lifecycle | SOTA, eval, or no skill | New public facade over `xllm-flow`, subject to Phase 3 decision |
| Performance optimization | SOTA, benchmark, profiler, pipeline | SOTA for open-ended iteration; specialists for fixed outcomes |
| Evaluation execution | eval, perf, accuracy, server | Select by workload breadth and service-only intent |
| Batch campaign | batch, eval, perf | Batch only for explicit matrix/repetition |
| Fair comparison | benchmark, eval, perf | Benchmark owns policy/conclusion; eval owns execution |
| Profiling | profiler, pipeline, SOTA | Profiler for capture/general analysis; pipeline for stage/rank/bubble |
| Accuracy regression | accuracy-debug, incident, accuracy runner | Accuracy-debug owns diagnosis; runner measures |
| Build/service failure | incident, build/server gate | Incident owns diagnosis; gate owns healthy verdict/maintenance |

## Known Baseline Gap

The lifecycle sentinel is intentional. Phase 1 would be dishonest if it selected a child skill for
mandatory `xllm-flow` state transitions. Phase 3 must either add a lifecycle facade or explicitly
justify another canonical owner using this corpus.

## Comparison Rule

Each Phase 3-5 change must name the affected case IDs. The final result passes when:

1. every sentinel is replaced by a real canonical skill;
2. expected primary ownership is unique;
3. internal/compatibility entries never appear as implicit primary;
4. all allowed and forbidden references resolve through the catalog;
5. no expected route overclaims framework/backend support.

## Phase 3 Result

- All five lifecycle sentinel cases now resolve uniquely to `xllm-experiment-lifecycle`.
- The original `current_primary_candidates` remain in the corpus as the before snapshot.
- SOTA is limited to open-ended optimization with measurable code iteration.
- Eval owns a mixed performance-and-accuracy suite; perf and accuracy runners retain explicit
  one-workload routes; batch owns only matrix or repeated campaigns; benchmark owns fairness and
  publishable conclusions.
- No probabilistic model-routing accuracy is claimed. The improvement is the removal of five
  missing canonical routes and a deterministic, test-enforced ownership boundary.
