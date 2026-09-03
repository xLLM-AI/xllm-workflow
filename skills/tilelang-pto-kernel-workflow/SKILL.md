---
name: tilelang-pto-kernel-workflow
description: 编排需要多轮修改 TileLang 或 generated PTO kernel 的昇腾 NPU 融合算子优化闭环：从真实模型 Profile、Golden/state 合同和公平 round0 开始，按单一 Plan/round 完成 TileLang 调优、PTO source/ISA 特化、生产接入以及 kernel、模型和精度验收。用于明确要求开发或持续优化 TileLang/PTO kernel、从 TileLang 生成 PTO、修改 PTO intrinsic/UB/event，或把这些工作组织成可复现实验时；不用于只执行一次 benchmark、只分析既有 Profile、只管理实验目录、定位生产事故，或只把已完成算子接入 xLLM。
---

# TileLang to PTO Kernel Workflow

## Strategy Gene

```yaml
signals_match:
  - 修改或持续优化 TileLang、generated PTO source、PTO kernel
  - 从真实模型热点组织多轮 Plan/round 实验
  - 工作涉及 state/owner/task-map、intrinsic/UB/event 或生产接入门禁
summary: 从真实 Profile 和正确性合同出发，每轮只验证一个主要机制，以证据决定通过、淘汰或补证，直到生产验收与经验回填闭环。
strategy:
  - 先锁定业务路径、Golden/state 合同和公平 round0，再提出 Plan
  - 一轮只选择一个 Plan、一个调优层次和一个主要变量
  - 严格执行 Select -> Implement -> Verify -> Review -> Decide
  - 只读取当前阶段需要的 reference；建档和结构校验交给 scripts
avoid:
  - 不在缺少目标 SoC Profile 或 source 证据时凭经验改 kernel
  - 不在同一 round 混改 TileLang/PTO 或多个主要机制
  - 不用 Simulator、裸 wall-clock 或单次最好值作性能结论
  - 不越过精度、state、资源、路由、Graph、fallback 门禁
  - 不另建顶层实验状态或与统一 run 的 CHECKPOINT、attempt ledger 竞争
  - 不覆盖用户改动、删除失败记录或外推案例参数
constraints:
  - 顶层 run 由 xllm-experiment-lifecycle 管理；Dashboard 只拥有算子工作包状态
  - 工作包状态仅限待实现、通过、淘汰
  - round 编号单调递增；失败、补证、组合、派生均建立新 round
  - candidate 可回退；通过前记录代码、source、object 身份
  - kernel、模型性能、任务精度分别测量和报告
validation:
  - 依次检查编译/source、Golden/state、资源、msprof A/B、跨 Shape、路由
  - 精度失败立即停止性能比较并进入 Decide
  - 每轮 validate_run.py 通过；最终再以 --final 校验
  - 至少一个 Plan 已裁决；final-evidence.json 对 A/B、精度、路由和 rollback artifact 做 SHA-256 绑定
  - 最终代码已复采，Dashboard 验收项全部关闭，生产路径与 rollback 已实测
```

## 按需读取

一次只加载当前步骤需要的主 reference：

| 任务 | 主 reference |
| --- | --- |
| 新建/恢复 run、artifact 所有权、阶段 Gate | [workflow-contract.md](references/workflow-contract.md) |
| 仲裁、裁决、组合、切换 PTO、停止条件 | [decision-rules.md](references/decision-rules.md) |
| TileLang 公式、schedule、Tile、owner、task map | [tilelang-playbook.md](references/tilelang-playbook.md) |
| `target="pto"`、source、intrinsic、UB、event | [pto-playbook.md](references/pto-playbook.md) |
| OPP/ACLNN/Graph、A/B、任务精度、rollback | [production-gates.md](references/production-gates.md) |
| Qwen3.5 GDN/state-owner 案例 | [qwen35-gdn-case.md](references/qwen35-gdn-case.md) |

案例只产生候选假设，不能替代当前 Shape、SoC/CANN、Profile 和 Golden。

当前 Gate 只按需委托一个最窄专项能力：顶层 run 状态用 `xllm-experiment-lifecycle`，
Profile 用 `xllm-npu-profiler`，正式 A/B 结论用 `xllm-npu-benchmark`，代码复核用
`xllm-npu-code-review`，模型与精度验收用 `xllm-npu-eval-runner`，已完成算子的 xLLM
接入用 `xllm-npu-xllm-ops-integration`。Catalog dependency 不表示同时注入这些 Skill。

## 启动或恢复

1. 搜索目标仓的 `AGENTS.md`、实现、构建、测试和 Profile；沿用仓库约定。
2. 从代码和 artifacts 获取算子、模型、SoC/CANN、Shape、dtype/layout、Graph/TP、测量口径和 rollback；只询问无法发现且会改变方案的信息。
3. 用 `xllm-experiment-lifecycle` 创建或恢复顶层 `$RUN_ROOT`；已有 run 先读其 CHECKPOINT 和 attempt ledger。
4. 读取 `$RUN_ROOT/analysis/tilelang-pto/<op>` 中的 Dashboard、progress、当前 Plan，从记录的 loop step 继续，不覆盖历史。
5. 缺少算子工作包时，在统一 run 下创建：

```bash
python3 <skill-dir>/scripts/init_run.py \
  --op <op-name> \
  --repo-root "$RUN_ROOT" \
  --output-root analysis/tilelang-pto
WORK_ROOT="$RUN_ROOT/analysis/tilelang-pto/<op-name>"
```

已有 kernel 也必须补齐 W0/W1。已有 PTO 还要证明生成入口和 TileLang baseline；只差生产接入也不能跳过公平 baseline、路由和 state replay。

## 外层闭环 W0-W8

| 阶段 | 必须产出 | 失败或下一跳 |
| --- | --- | --- |
| W0 合同 | 业务路径、Golden/state、副作用、测量口径、rollback | baseline 不可复现则留在 W0 |
| W1 round0 | 目标 SoC msprof、调用次数、热点源码映射 | 覆盖不足则回 W0/W1 |
| W2 诊断 | 观察、假设、单一改动、预期指标、风险、验证/回退 | 证据不足则补 Profile/source |
| W3 仲裁 | 唯一首推、why-not、互斥/叠加、Plan 文件 | 无可证候选则回 W1/W2 |
| W4 实施 | 单层次/单机制 diff、开关、source/object hash | 失败也进入 W6 记录和回退 |
| W5 验证 | 精度、资源、msprof A/B、跨 Shape、route/Graph | 硬 Gate 失败立即进入 W6 |
| W6 裁决 | 通过/淘汰/待实现、回退、派生、下一 round | 仍有 Plan 则回 W3/W4 |
| W7 生产 | 最终复采、OPP/ACLNN/Graph、kernel/model/accuracy、rollback | 失败则派生 Plan 并回 W3 |
| W8 回填 | 有来源、收益和边界的 `backfill-draft.md` | 审阅后才能写回规则库 |

## 内层闭环 One Plan Per Round

每轮把 step、证据、verdict 和 next 同步到 Plan、Dashboard、progress：

```text
R{N}.1 SELECT     冻结 baseline、唯一变量、验收线、复采项、rollback
R{N}.2 IMPLEMENT  只改一个层次/机制；完成最小编译和精度自检
R{N}.3 VERIFY     source -> Golden/state -> 资源 -> msprof/A-B -> Shape/route
R{N}.4 REVIEW     核对路径命中、因果证据、精度、资源、副作用、噪声
R{N}.5 DECIDE
  PASS       更新 baseline -> 新 round
  ELIMINATE  回退 -> 下一候选或派生 Plan -> 新 round
  PENDING    只定义一个缺失证据 -> 新 round
```

不得跳过 Decide 或覆盖旧 round。组合两个通过 Plan 时，把组合当作新 candidate，分配新 round并重跑全部适用 Gate。

## 验证与收尾

```bash
python3 <skill-dir>/scripts/validate_run.py "$WORK_ROOT"
python3 <skill-dir>/scripts/validate_run.py "$WORK_ROOT" --final
```

性能结论必须来自目标 SoC 的同口径 fresh A/B 或 ABBA；source audit 解释机制，msprof 证明时间变化。最终答复列出通过/淘汰 Plan、kernel/模型/任务精度、rollback、风险、artifact 路径和未完成 Gate；未执行不得写成通过。
