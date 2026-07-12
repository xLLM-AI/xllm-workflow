# PR13 Fresh-Task Skill Routing Dogfood

Date: 2026-07-12

PR: `xLLM-AI/xllm-workflow#13`

Observed HEAD before probes: `e5763bf10cacf65e8c342b45384bdac045f4f592`

## Method and Guardrails

- Checked out the latest `refactor/skill-taxonomy-routing` HEAD and confirmed a clean worktree.
- Refreshed 21 canonical Codex skill links and validated the catalog with no broken links.
- Ran every prompt in a fresh isolated subagent with no shared probe context.
- Each subagent received exactly one raw prompt plus the routing-only restriction. No command,
  file mutation, service launch, SSH connection, or NPU workload was allowed.
- The observations below were recorded before reading `expected_primary` from the routing
  specification. Expected values and comparison results were added only afterward.

## Sealed Raw Observations

| Case | Prompt | Observed primary skill | Observed implicit skills | Allowed followups | Observed rationale |
|---:|---|---|---|---|---|
| 1 | 为一个新的性能实验创建可恢复的 run root。 | `xllm-experiment-lifecycle` | None | `xllm-npu-perf-runner`; `xllm-npu-sota-loop` only if the scope becomes iterative optimization | Creating a resumable run root is lifecycle control-plane work, not a workload or fairness review. |
| 2 | 读取 CHECKPOINT 并恢复昨天中断的实验。 | `xllm-experiment-lifecycle` | None | Phase-dependent specialist runners, server manager, profiler, or benchmark | CHECKPOINT restore and run resumption belong to lifecycle; workload execution remains delegated. |
| 3 | 验证 evidence 并 finalize 这个 run。 | `xllm-experiment-lifecycle` | None | None required | Evidence validation and finalization are lifecycle control-plane responsibilities. |
| 4 | 系统优化 Qwen3.5 TP2 decode latency，建立基线并持续迭代。 | `xllm-npu-sota-loop` | `model-pr-optimization-history` | `xllm-experiment-lifecycle`, server/perf/profiler/pipeline/benchmark/simulation/report specialists; kernel skill only if evidence selects that path | A quantified, open-ended baseline-to-profile-to-implementation-to-A/B loop is SOTA-loop scope. History was identified as a Learn-stage implicit dependency. |
| 5 | 对已经 ready 的服务只跑一次 EvalScope 性能测试。 | `xllm-npu-perf-runner` | `xllm-npu-server-manager` identified as an already-satisfied prerequisite, not invoked | `xllm-npu-benchmark` only for later fairness or publishable claims | One performance workload against an already-ready service is the single-run perf runner boundary. |
| 6 | 启动已构建服务，跑性能和精度并收集完整 artifacts。 | `xllm-npu-eval-runner` | None | `xllm-experiment-lifecycle`, `xllm-npu-server-manager`, perf/accuracy runners, report writer | Service plus performance plus accuracy plus complete artifacts is the mixed eval orchestrator boundary. |
| 7 | 批量跑三个模型的 TP1 和 TP2 性能矩阵。 | `xllm-npu-batch-perf` | `xllm-experiment-lifecycle` | server manager, perf runner, report writer, benchmark; build gate if binary identity must be established | Multiple models and TP configurations form a batch performance campaign. |
| 8 | 审查已有 before/after 数据是否公平，收益能否写进 PR。 | `xllm-npu-benchmark` | None | Perf/batch runners or server manager for missing evidence; lifecycle/reporting for formalization; profiler/pipeline only for mechanism explanation | Fairness and publishable before/after claims are benchmark policy and verdict work. |
| 9 | 采集一次 msprof 并生成五表报告。 | `xllm-npu-profiler` | None | `xllm-npu-report-writer` only for later integration into a broader report | msprof capture and the five-table report are profiler responsibilities. |
| 10 | 分析已有 profile 的 rank timing 偏斜和 allgather gap。 | `xllm-npu-pipeline-analysis` | None | `xllm-npu-profiler` only for additional kernel/overlap statistics | Existing-profile rank skew and collective gaps are pipeline/timeline analysis, not a new profiling campaign. |
| 11 | rebase 后 setup.py build 链接失败，排查 submodule 或缓存污染。 | `xllm-npu-incident-triage` | None | `xllm-npu-build-gate` after diagnosis | A post-rebase link failure with suspected submodule/cache contamination is incident diagnosis; build gate verifies the repaired state. |
| 12 | 验证当前 checkout 能否确定性构建并输出 binary provenance。 | `xllm-npu-build-gate` | None | `xllm-experiment-lifecycle` only if provenance must enter a formal run | Deterministic build identity and binary provenance are the build gate contract. |
| 13 | 只启动服务，完成 ready、真实 smoke 和 cleanup 证明。 | `xllm-npu-server-manager` | None | Incident triage on failure; lifecycle only if a formal run is later requested | Launch, ready, real generation smoke, and cleanup evidence are exactly the service lifecycle boundary. |
| 14 | 显式使用 `$ssh-remote-exec` 在远程主机执行 `uname -a`。 | `ssh-remote-exec` | None | None | Explicit skill invocation wins; the probe correctly stopped without making an SSH connection. The isolated agent also reported that the refreshed skill was not present in its static available-skill list, despite selecting the explicit skill. |

## Specification Comparison

The specification was opened only after the raw observations above were saved.

| Case | Expected primary | Match / mismatch | Mismatch root cause | Scope overclaim |
|---:|---|---|---|---|
| 1 | `xllm-experiment-lifecycle` | Match | None | No |
| 2 | `xllm-experiment-lifecycle` | Match | None | No |
| 3 | `xllm-experiment-lifecycle` | Match | None | No |
| 4 | `xllm-npu-sota-loop` | Match | None | No; the observed history lookup was a public Learn-stage dependency, not a primary route. |
| 5 | `xllm-npu-perf-runner` | Match | None | No; server-manager was described only as an already-satisfied prerequisite and was not invoked. |
| 6 | `xllm-npu-eval-runner` | Match | None | No |
| 7 | `xllm-npu-batch-perf` | Match | None | No; lifecycle was identified as optional control-plane support, not as the campaign owner. |
| 8 | `xllm-npu-benchmark` | Match | None | No |
| 9 | `xllm-npu-profiler` | Match | None | No |
| 10 | `xllm-npu-pipeline-analysis` | Match | None | No |
| 11 | `xllm-npu-incident-triage` | Match | None | No |
| 12 | `xllm-npu-build-gate` | Match | None | No |
| 13 | `xllm-npu-server-manager` | Match | None | No |
| 14 | `ssh-remote-exec` | Match | None | No; this was an explicit invocation, not implicit routing. |

## Acceptance Summary

- Observed primary match rate: **14/14 (100%)**.
- Lifecycle create/resume/finalize: **3/3 (100%)** to `xllm-experiment-lifecycle`.
- Open-ended optimization: **1/1** to `xllm-npu-sota-loop`.
- Single performance, mixed eval, batch, benchmark, profiler, and pipeline: **6/6** to their
  corresponding specialist skills.
- Build incident, deterministic build, and service-only maintenance: **3/3** to incident triage,
  build gate, and server manager respectively.
- Ordinary prompts implicitly selecting `ssh-remote-exec`: **0**.
- Explicit `$ssh-remote-exec` availability: **1/1 primary selection**. The isolated agent reported
  that the refreshed skill was absent from its static available-skill list, which is consistent
  with refresh metadata becoming visible only to newly created top-level tasks; explicit naming
  still selected the requested skill. No SSH command was executed.
- Internal skill as implicit primary: **0**.
- Primary mismatches: **none**.
- Scope overclaims: **none**.

The dogfood therefore meets the requested 90% threshold without changing `expected_primary` or any
runtime/skill routing implementation. No mismatch-driven SKILL.md change or failed-case retest was
needed.
