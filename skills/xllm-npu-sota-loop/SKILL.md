---
name: xllm-npu-sota-loop
description: 系统化推进 xLLM NPU 性能优化闭环，从目标定义、基线、profiling、实现、review、验证到最终沉淀。适用于需要持续提升 xLLM NPU 推理性能或建立可复用优化流程的任务。
---

# xLLM NPU SOTA 优化闭环

使用本 skill 处理端到端 xLLM NPU 优化任务。它的目标不是让 agent 直接写
patch，而是先建立公平基线、收集证据、选择端到端收益最大的可验证假设、验证结果，
最后沉淀可复用经验。

本流程借鉴 PolyArch/humanize 中“独立 review + 迭代反馈”的纪律，但不是
Humanize RLCR 实现本身。本仓库使用面向 xLLM NPU 的 evidence loop：

```text
Research -> Learn -> Code -> Review -> Validate -> Record
```

## Phase 0: 目标与环境

先明确优化目标，再开始实验。

必须记录：

- 模型和 tokenizer；
- dtype、量化、图模式、投机解码和框架参数；
- NPU 型号和卡数；
- 框架 commit 和启动命令；
- workload、采样参数、并发、SLA 和 artifact root；
- 精度与性能的验证门禁。

从统一 schema 创建实验，不手工创建另一套目录：

```bash
cp reference/io_specs/experiment.example.yaml experiment.yaml
# 填写真实 repo/commit/binary/model/workload/run_root 后执行
python scripts/xllm_flow.py preflight --spec experiment.yaml --output "$RUN_ROOT/env"
python scripts/xllm_flow.py run create --spec experiment.yaml
```

`run create` 生成 manifest、CHECKPOINT、attempt hash chain、Big-Rock gate 和 ledger
骨架。manifest 字段参考 `../../reference/io_specs/run-manifest-template.md`。

## Phase 0.5: 查询历史

改代码前先查模型和 PR 历史：

```text
Use `reference/pr_history/` to query prior work for <model_name>,
related operators, risky source paths, failed attempts, and known validations.
```

把有效结论写入 run root，例如：

```text
$RUN_ROOT/history/model-history-notes.md
```

Qwen3.5/MTP 相关材料只是可选历史参考。只有当前任务涉及该模型族或投机解码时
才加载。

## Phase 1: 公平基线

在改代码前先启动服务并收集 warmed-up baseline。

baseline 完成后立即写入 ledger：

```bash
python scripts/xllm_flow.py attempt add --run-root "$RUN_ROOT" --spec experiment.yaml \
  --attempt-id baseline-r0 --phase benchmark --status pass --hypothesis baseline \
  --metrics-json "$RUN_ROOT/reports/baseline-metrics.json" \
  --artifact reports/baseline-metrics.json --repeat-index 0
```

使用：

- `../xllm-npu-eval-runner/SKILL.md`：服务启动和 evalscope artifact 收集；
- `../xllm-npu-benchmark/SKILL.md`：公平性检查和结果对比。

规则：

- 使用相同模型、tokenizer、dtype、硬件、workload、采样参数和 SLA；
- 每个被比较框架都要独立调优；
- 保留失败候选和失败原因；
- 记录完整启动命令；
- 保存原始 benchmark 输出和归一化 summary。

如果同一任务要比较多个 PR 或候选分支，先建立一个固定 eval lane 和可复用
build tree，再让每个候选基于同一 main/base commit 增量重编。不要把不同
候选放在互相独立、不可复用构建产物的目录里，除非用户明确接受额外编译时间。
候选分支的构建日志、二进制 `file`/`ldd`、必要本机 patch 和所有环境绕过步骤
必须写入 run manifest。

性能产物应满足：

- `../../reference/io_specs/perf-artifact-schema.md`
- `../../reference/io_specs/run-manifest-template.md`

## Phase 2: 差距判断

用基线判断是否需要继续优化。

```text
gap = (reference_throughput - target_throughput) / reference_throughput
```

如果目标已经达成，记录结果并停止。如果差距明确，进入证据采集。

同时把差距转换成绝对预算，例如“还差 3.2 ms TPOT”。每轮必须并列显示
baseline、当前 best、目标和剩余差距，避免用几十微秒局部收益掩盖毫秒级缺口。

## Phase 3: 证据采集

选择 patch 前必须先收集解释差距的证据。

默认使用 `../xllm-npu-profiler/SKILL.md` 做 profiling。根据症状补充：

- `../xllm-npu-pipeline-analysis/SKILL.md`：prefill/decode 边界、decode 空泡、层耗时、rank skew；
- `../xllm-npu-capacity-planner/SKILL.md`：HBM、KV cache、并发容量和 OOM 风险；
- `../xllm-npu-compute-simulation/SKILL.md`：FLOPs、MFU 和硬件理论下界；
- `../xllm-npu-accuracy-debug/SKILL.md`：乱码输出、分数下降、GPU/NPU 不一致；
- `../xllm-npu-incident-triage/SKILL.md`：crash、hang、图模式失败、HCCL 问题。

profiling 是诊断证据，不能替代正式的非 profiling 前后性能对比。

### Phase 3.5: Big-Rock Gate

选择 patch 前必须执行 `references/big-rock-optimization-gate.md`：

1. 建立端到端 loss budget，覆盖主计算、通信、host、graph/sync、copy 和 sampling；
2. 按 L0 架构算法、L1 pipeline/stage、L2 layer/operator、L3 kernel/detail
   从大到小检查；
3. 用“受影响预算 × 可消除比例”估算端到端收益区间并排序；
4. 默认选择能关闭至少 20% 剩余目标差距的候选；
5. L0-L2 未量化或未被证据否决前，不得进入 L3 微优化。

门禁状态只能是 `PASS / DISCOVERY / BLOCKED / EXEMPT`。`DISCOVERY` 最多允许两轮
有明确测量目标的证据采集；之后必须转为 PASS、BLOCKED 或有理由的 EXEMPT。
进入 `implementation/code/patch` checkpoint 前必须运行：

```bash
python scripts/xllm_flow.py gate check --run-root "$RUN_ROOT"
```

必须生成：

```text
$RUN_ROOT/analysis/bottleneck-budget.md
$RUN_ROOT/analysis/candidate-ranking.md
$RUN_ROOT/analysis/big-rock-gate.json
```

如果最大 bucket 仍是 `unclassified`，继续做粗粒度归因，不得通过放大 timeline
局部细节绕过门禁。

## Phase 4: 优化计划

计划必须从证据导出，而不是凭直觉直接写 patch。

计划应包含：

- 根因假设；
- 相关源码路径或框架组件；
- 下一轮只验证一个根因假设；一个假设可以跨模块，不得把“单一假设”误解为
  “必须选择最小代码改动”；
- 跨模块修改必须共享一个因果机制、一个联合 A/B 或禁用开关和清晰 rollback
  边界；否则拆成多个阶段；
- 预期收益；
- 精度、内存、图模式、通信和兼容性风险；
- 精确的验证命令和必须产出的 artifact。
- 最大可行动 loss bucket，以及更大 bucket 为什么不可行动；
- 端到端收益区间、噪声下限和占剩余目标差距的比例；
- 当前层级 L0/L1/L2/L3，以及是否满足下钻条件。

建议写到：

```text
$RUN_ROOT/humanize/refined-plan.md
```

如果 profiling 指向 decode graph replay 前的 host bubble，优先加载
`references/replay-input-overlap.md`，先判断能否把 replay input / metadata
prepare 移到 schedule-overlap 窗口中。除非已有独立 A/B 证据，不要把 custom
kernel、async D2H、LmHead setup cache、raw metadata copy 等多个实验合并进同一个
上库 PR。

算子工作使用具体专项 skill：Triton-Ascend AOT 迁移用
`../xllm-npu-triton-migration/SKILL.md`；已有 xllm_ops 接入 runtime 用
`../xllm-npu-xllm-ops-integration/SKILL.md`。

## Phase 5: Evidence Loop 迭代

每轮按这个顺序执行：

```text
Research: 更新 loss budget，选择端到端收益最大的可行动假设
Learn:    查询模型历史和已有失败尝试
Code:     实现一个可 review 的修改
Review:   执行 NPU 专项代码审查
Validate: 重新构建、测试、benchmark、profiling，并按需检查精度
Record:   更新 run ledger 和可复用 reference
```

每轮 Validate 后重算 loss budget 和候选排序。若连续两轮收益低于噪声，或小优化
累计收益上限不足以关闭 20% 剩余差距，立即停止细节迭代并返回 L0/L1。

候选 A/B 完成后用 `attempt add` 写入 `--parent-attempt <baseline-id>`、至少一个
`--changed-variable` 和 `--decision accept/reject`。接受候选的 metrics JSON 必须同时
保存 `baseline`、`current` 和 `delta`；只有 baseline 的 run 不能以性能优化 PASS 收口。

推荐 skill 路由：

| 阶段 | 推荐 skill | 产物 |
|---|---|---|
| Research | `xllm-npu-benchmark`, `xllm-npu-profiler`, `xllm-npu-pipeline-analysis`, `xllm-npu-capacity-planner`, `xllm-npu-compute-simulation`, `xllm-npu-accuracy-debug` | 证据摘要 |
| Learn | `reference/pr_history/` | 相关历史和风险 |
| Code | `xllm-npu-triton-migration`, `xllm-npu-xllm-ops-integration`, 目标仓库本地 skill | 一个 patch 或实验 |
| Review | `xllm-npu-code-review`, 目标仓库 review 规则 | 分级 review findings |
| Validate | `xllm-npu-eval-runner`, `xllm-npu-benchmark`, `xllm-npu-profiler`, `xllm-npu-accuracy-debug`, `xllm-npu-incident-triage` | 验证报告 |
| Record | `xllm-npu-sota-loop`, `humanize/`, `reference/pr_history/` | attempt ledger、optimization ledger、可复用经验 |

## 验证要求

选择能证明或否定当前修改的最小验证集合。

常见门禁：

- build 通过；
- 相关单测或集成测试通过；
- 可能影响正确性时，跑精度 smoke 或数据集子集；
- warmed-up 性能复测体现预期趋势；
- 以性能为目标时，profiling 能解释性能变化；
- 没有带入无关文件或私有环境信息。

## 停止条件

满足任一条件即可停止：

- 达到或超过目标；
- 结果落入约定的平局阈值；
- profiling 证明瓶颈是当前范围外的硬件或框架限制；
- 连续三轮 evidence loop 都没有改善；
- 下一步依赖当前环境没有的外部决策、硬件或数据。

更多细节见 `references/stop-conditions.md`。

## 最终输出

闭环结束时交付：

- final benchmark summary；
- final root-cause 或 bottleneck 解释；
- validation summary；
- patch summary；
- known risks 和 follow-up work；
- run-root ledger 更新。

具体 ledger 写入 run root，不写回本仓库：

```text
$RUN_ROOT/humanize/attempt-ledger.md
$RUN_ROOT/humanize/optimization-ledger.md
$RUN_ROOT/humanize/source-idea-ledger.md
$RUN_ROOT/humanize/lineage.jsonl
```

结束前执行统一验证和收口；performance optimization 必须已有通过或豁免的
`big-rock-gate.json`、至少一个通过的 benchmark attempt，并完成 retention review：

```bash
python scripts/xllm_flow.py run validate --run-root "$RUN_ROOT" --status pass
python scripts/xllm_flow.py run finalize --run-root "$RUN_ROOT" --status pass \
  --reviewed-by "$USER" --retention-decision keep
```

## 可选历史参考

仅在当前任务相关时加载：

- `references/replay-input-overlap.md`
- `references/big-rock-optimization-gate.md`
- `references/qwen35-mtp-case.md`
- `references/mtp-transpose-elimination-case.md`
- `../xllm-npu-benchmark/references/mtp-benchmark-lessons.md`
- `../xllm-npu-profiler/references/mtp-profiling-lessons.md`
- `../../reference/pr_history/qwen3-1p7b.md`
- `../../reference/pr_history/qwen35-mtp.md`
