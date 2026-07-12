---
name: xllm-experiment-lifecycle
description: xLLM 实验生命周期入口。用于创建或恢复 run root、执行 preflight、维护 CHECKPOINT 和 attempt ledger、验证 evidence、finalize 以及 archive。面对“新建实验、继续中断任务、验证并收口、归档 run”等控制面请求时优先使用；不负责选择性能优化方案、执行 benchmark workload、启动服务或分析 profiler。
---

# xLLM 实验生命周期

本 skill 是 `scripts/xllm_flow.py` 的公开门面。它统一管理实验状态和证据链，专项
工作仍委托给对应 skill，不复制 build、service、benchmark、accuracy 或 profiling
实现。

## 路由边界

优先使用本 skill：

- 从 `experiment.yaml` 创建可恢复的 run root；
- 读取 `CHECKPOINT.md` 恢复中断任务；
- 记录候选 attempt、fingerprint 和 ledger；
- 验证 run evidence 并 finalize；
- 完成 retention review 后 archive。

不要使用本 skill 作为以下请求的主入口：

- 开放式、多轮性能优化：`xllm-npu-sota-loop`；
- 单次性能或精度 workload：对应 runner；
- 公平 before/after 或跨框架结论：`xllm-npu-benchmark`；
- 服务、构建、profiling 或事故专项任务：对应 specialist。

## 标准流程

```bash
python scripts/xllm_flow.py preflight --spec experiment.yaml --output "$RUN_ROOT/env"
python scripts/xllm_flow.py run create --spec experiment.yaml
# 恢复时读取 "$RUN_ROOT/CHECKPOINT.md"，推进阶段时使用 checkpoint 子命令。
# 专项 skill 执行 build -> service -> benchmark，并通过 attempt add 记录结果。
python scripts/xllm_flow.py run validate --run-root "$RUN_ROOT"
python scripts/xllm_flow.py run finalize --run-root "$RUN_ROOT" --status pass \
  --retention-decision keep
python scripts/xllm_flow.py run archive --task-id "$TASK_ID"
```

实际参数以各子命令 `--help` 为准。不要绕过 `preflight`、`run validate` 或 evidence
gate 手工修改最终状态。

## 恢复与委托

恢复任务时先读取 run root 中的 manifest、`CHECKPOINT.md`、attempt ledger 和
fingerprint，再从最后一个未完成 checkpoint 继续。不得重复执行已经完成且 fingerprint
相同的候选，除非显式记录 repeat index。

生命周期顺序是：

```text
experiment -> preflight -> run create -> build -> service -> benchmark
           -> evidence -> run validate -> finalize -> archive
```

其中 build、service、benchmark 和专项分析由 catalog 中对应 skill 执行；本 skill
负责确保它们的 verdict 和 artifacts 被生命周期命令消费。

## 完成标准

- run root 可由 manifest 和 checkpoint 恢复；
- 每个候选都有 fingerprint、changed variable、metrics 和 decision；
- `run validate` 通过且 evidence verdict 可审计；
- finalize 不发生在 build、service、fairness 或 evidence gate 失败之后；
- archive 前已经记录 retention 决策。
