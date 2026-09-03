# Workflow Contract

## 目录

1. 角色与状态所有权
2. Artifact 布局
3. 阶段合同
4. Profile 诊断输入
5. 最终验收
6. 最终 Evidence 合同

## 1. 角色与状态所有权

顶层实验状态由 `xllm-experiment-lifecycle` 和统一 run 的 CHECKPOINT、attempt ledger 管理；本 Skill 只拥有 `$RUN_ROOT/analysis/tilelang-pto/<op>` 算子工作包。无论诊断、实现和复核是否由不同 Agent 或同一 Agent 的不同阶段完成，都遵守：

- `plan-dashboard.md` 只由 workflow owner 更新，是 Plan 状态真相源。
- `progress.md` 保存跨轮上下文和过程，不保存权威状态。
- `plans/plan-<id>.md` 保存单 Plan 的完整证据和历史。
- analyzer 只诊断，implementer 只实现当前 Plan，reviewer 不改代码。
- 详细日志、CSV 和 source 不贴进 Dashboard，只记录路径与摘要。

## 2. Artifact 布局

```text
$RUN_ROOT/analysis/tilelang-pto/<op>/
├── baseline.md
├── plan-dashboard.md
├── progress.md
├── manifest.json
├── analysis/
│   ├── memory.md
│   ├── sync.md
│   ├── compute.md
│   ├── task-map.md
│   ├── precision.md
│   └── arbitration.md
├── plans/
│   └── plan-<id>.md
├── source-audit/
│   ├── tilelang/
│   └── pto/
├── precision/
│   ├── golden/
│   └── atk/
├── perf/
│   ├── round0/
│   ├── roundN/
│   └── final/
├── model/
│   ├── graph-route/
│   ├── rollback/
│   └── tpot/
├── final-report.md
├── final-evidence.json
└── backfill-draft.md
```

用 `scripts/init_run.py --repo-root "$RUN_ROOT" --output-root analysis/tilelang-pto` 创建骨架。已有目录中只补缺失文件，不覆盖实验记录；顶层生命周期变化仍写入统一 CHECKPOINT 和 attempt ledger。

## 3. 阶段合同

| 阶段 | 必要输入 | 动作 | 证据 | Gate |
| --- | --- | --- | --- | --- |
| W0 场景锁定 | 模型路径、SoC/CANN、Shape 类别、dtype/layout | 固定 Golden、测量方法、框架配置与回退 | `baseline.md` | 原路径精度/性能可重复 |
| W1 round0 | 可运行 baseline | 采集目标 SoC msprof | `perf/round0/`、调用次数、热点映射 | 业务路径完整 |
| W2 诊断 | 同一 Profile、源码、Golden | 五视角独立诊断 | `analysis/*.md` | 候选有机制证据 |
| W3 仲裁 | 全部候选 | 排序、互斥/叠加、唯一首推 | `arbitration.md`、Plan 文件 | 唯一变量和验收口径明确 |
| W4 实施 | 当前 baseline、当前 Plan | 修改一个调优层次和一个主要机制 | diff、source/object hash | 可编译、可回退 |
| W5 验证 | candidate | 精度、source、资源、msprof、A/B | `precision/`、`perf/roundN/` | 同口径且跨 Shape |
| W6 裁决 | 本轮全部证据 | 通过/淘汰/保持待实现、派生 | Dashboard 和 Plan round | 只有通过可推进 baseline |
| W7 生产 | 最终组合 | OPP/ACLNN/Graph/model/accuracy | `final-report.md`、`model/` | 路由正确、报告分层 |
| W8 回填 | 通过/淘汰历史 | 抽象规则与边界 | `backfill-draft.md` | 审阅后写回 |

## 4. Profile 诊断输入

round0 与复采轮至少固定：

| 类别 | 字段 |
| --- | --- |
| 软件 | 代码 commit、TileLang/PTO commit、CANN、编译选项 |
| 硬件 | SoC、核心数、频率/功耗模式、设备健康 |
| 输入 | Shape 类别、dtype、layout、稀疏度、state 索引 |
| 框架 | eager/Graph、TP、并发、schedule overlap、fallback 开关 |
| 测量 | warmup、重复次数、同步方法、A/B 顺序、统计口径 |
| 资源 | UB/L1/L0、Workspace、Buffer/event 数、Core/task map |
| 结果 | 中位延迟、min/max 或波动、Task Duration、精度误差 |

真实硬件回答“是否变快”，流水图与 generated source 回答“为什么变化”。两类证据必须能互相解释。

诊断视角：

- **memory**：GM 字节、TLOAD/TSTORE、MTE2/MTE3、连续性、重复搬运、片上复用。
- **sync**：barrier、flag/event、owner 交接、ready/free、时间线气泡。
- **compute/instruction**：Vector/Cube/Scalar、Reduce/Broadcast、融合指令、无效计算。
- **task-map/tiling**：活跃核心、每核任务、尾波、Tile/stages、资源与并行度。
- **precision**：舍入点、累加 dtype、state/cache 副作用、原地更新、Graph 地址。

每份诊断只输出主判断、证据、置信度和候选四元组：

```text
预期收益 / 风险 / 改动面 / 证据强度
```

## 5. 最终验收

进入最终验收前确认：

- `plan-dashboard.md` 至少有一个 `plan-<id>` 数据行，所有 Plan 已裁决，最终验收项全部勾选且 step 为 `CLOSED`。
- `final-evidence.json` 的 `performance_ab`、`precision`、`route`、`rollback` 均为 `pass`，并用 SHA-256 绑定对应目录下非空 JSON artifact。
- 没有 `待实现` Plan，或所有未做项都明确转为淘汰并写原因。
- 最终代码已复采，配置与 round0 一致。
- 每个通过 Plan 都存在于最终代码路径。
- 每个淘汰 Plan 已回退或由开关关闭。
- 可叠加 Plan 的组合版本已经实测。
- Host dispatch、JIT/AOT、OPP、ACLNN 和 Graph 加载同一语义版本。
- kernel baseline、公平模型 A/B 和精度边界分别报告。
- rollback 已实际检查，不只记录环境变量名称。

最终报告禁止：

- 用 Simulator 绝对时间代替目标 SoC。
- 只给最好一次耗时。
- 把某个 Shape 的参数描述为全局最优。
- 把 kernel speedup 直接写成模型 TPOT speedup。
- 把 Golden/ATK/模型 smoke 写成任务精度已完成。

## 6. 最终 Evidence 合同

从 `assets/final-evidence-template.json` 生成的 `final-evidence.json` 是机器可读的最终门禁：

- `schema_version` 固定为 `1`，`work_package_schema_version` 与 `manifest.json` 一致。
- `verdict` 必须为 `pass`；`plans.passed` 和 `plans.eliminated` 必须与 Dashboard 完全一致。
- `performance_ab`、`precision`、`route`、`rollback` 四个 check 必须为 `pass`。
- 每个 check 指向规定目录中的非空 JSON artifact；artifact 自身必须包含 `schema_version: 1` 和 `verdict: pass`。
- `sha256` 必须与 artifact 当前内容一致。修改或复采 artifact 后必须同步更新摘要和哈希。

validator 只接受 schema v2，对 schema v1 和未知版本一律失败。迁移旧工作包时，用 `init_run.py` 新建 v2 工作包，复制证据并按当前模板重建 Dashboard、Plan 和 `final-evidence.json`；不要只修改旧 manifest 的版本号。schema v2 强制 Dashboard loop 字段、Plan Round Loop、`perf/final/` 和 `model/rollback/`。
