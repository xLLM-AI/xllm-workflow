# PR12 Routing Conflicts

Baseline: `main@8e0a37e`. Severity reflects primary-route ambiguity, not runtime correctness.

## Facts

1. `xllm-flow` is mandatory for new experiment lifecycle operations but has no `SKILL.md` facade.
2. All 19 skills are listed or referenced by AGENTS, prompts, or another skill; none is wholly unreachable.
3. AGENTS exposes orchestrators, runners, gates, analyzers and support skills at one flat routing level.
4. Prompt templates sometimes contradict skill boundaries, for example service smoke routed to eval-runner.
5. Fairness/evidence/checksum/projection are deterministic scripts/functions, not skills.
6. `reference/pr_history/SKILL.md` is skill-like and validated, but is not installed by the current `skills/*` enumerator.

## Conflicts

| Severity | Competing routes | Ambiguous intent | Evidence | Current impact | Phase 1 cases needed |
|---|---|---|---|---|---|
| P0 | missing lifecycle vs SOTA/eval/batch/benchmark | create, resume, finalize or archive an experiment | `AGENTS.md:78-89`; `scripts/README.md:24-81`; no matching skill directory | lifecycle can be skipped or duplicated by child orchestrators | lifecycle create/resume/finalize/archive |
| P0 | SOTA vs benchmark/profiler/pipeline/eval | optimize TPOT, analyze decode gap, validate MTP | SOTA description/body and `prompts/xllm-npu-sota-loop-prompts.md` | fixed analysis can enter an open-ended code loop; optimization can start too low | optimization, profile-only, pipeline-only, benchmark-only, regression |
| P1 | eval vs perf/accuracy/server | run evaluation, run CEval, run perf, service smoke | eval boundary table; perf/accuracy independent wording; eval prompt line 6 | runner/orchestrator co-primary selection | mixed eval, perf-only, accuracy-only, service-only |
| P1 | batch-perf vs eval/perf | repeat one model, multiple models/TP, stability campaign | batch description; eval prompts lines 154-204 | workload shape becomes a competing top-level capability | one perf run, matrix, repeated campaign |
| P1 | benchmark vs eval | run and compare candidates vs review existing results | benchmark boundary `SKILL.md:10-17` | benchmark may appear to own raw execution | existing A/B, run-and-compare, SLA search |
| P2 | profiler vs pipeline-analysis | capture profile, generic bottleneck, decode bubble/rank skew | profiler `SKILL.md:12-34`; pipeline `SKILL.md:8-20` | both may be selected as co-primary | capture, five-table, existing-trace bubble/rank |
| P2 | incident vs accuracy/profiler | accuracy anomaly, performance regression, crash/build failure | incident body categories vs narrower description | broad incident body can absorb specialist work | score regression, perf regression, crash, build failure |
| P3 | report writer vs parent workflow | generate report during eval vs summarize completed artifacts | report `SKILL.md:10-38,87-132`; AGENTS direct route | support implementation can become co-primary | explicit report-only and broader experiment |
| P3 | build/service gate vs parent workflow | build or launch as maintenance vs full experiment | AGENTS direct routes and eval/SOTA dependencies | legitimate direct maintenance is hard to distinguish from delegated gate | direct build, build failure, direct service, service crash |

## Inferences

- A public lifecycle facade is likely justified because the underlying interface already owns many stable state transitions and is mandatory across multiple callers.
- SOTA should remain an optimization orchestrator but needs negative intents for fixed-scope analysis and evaluation.
- Perf and accuracy remain distinct because their inputs, outputs and correctness semantics differ; visibility should be measured rather than decided from naming.
- Batch implementation has value for campaign matrices, but its current name describes workload shape rather than outcome.
- Profiler and pipeline analysis should remain distinct; no merge evidence exists.
- Report writer and direct build/service maintenance each have a narrow independent user intent, so automatic internalization would be premature.

## Preliminary Recommendations

1. Add routing baseline before changing names or visibility.
2. Add one catalog as the machine-readable taxonomy source rather than duplicating fields across documents.
3. If baseline confirms it, introduce a public lifecycle facade that delegates to `xllm-flow` without scripts.
4. Preserve all current names during the first migration cycle; any new canonical name requires a tested compatibility redirect.
5. Keep xLLM as the primary framework scope and describe vLLM-Ascend/SGLang only at the verified adapter/artifact level.
6. Keep fairness/evidence/parser/snapshot/checksum/projection as internal deterministic implementations.

## Negative Routing Candidates

- SOTA: not for one trace analysis, one A/B review, one eval run, or incident reproduction.
- Eval: not for service-only maintenance, fair comparison, profiling interpretation, or root-cause diagnosis.
- Batch: not for one ordinary performance run.
- Benchmark: not for raw EvalScope execution without comparison or evidence claim.
- Profiler: not for an existing-trace stage/rank/bubble question when artifacts are already sufficient.
- Pipeline analysis: not for trace collection or generic five-table profiling.
- Incident: not for stable CEval regression or normal performance analysis after reproduction.
- Report writer: not primary while another workflow owns the requested experiment outcome.
- Build/service gates: not co-primary under a complete experiment request; preserve explicit maintenance routes.
