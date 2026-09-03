# TileLang Optimization Playbook

## 目录

1. 基线与 Bound
2. 候选动作顺序
3. 症状—动作表
4. 每轮 source audit
5. Autotune 与 Shape 分派
6. 切换信号

## 1. 基线与 Bound

TileLang 优化同时满足正确、变快、稳定和资源合法。排除首次编译和缓存影响，固定 warmup、重复次数和同步方法。

性能同时报告：

```text
延迟下降率 = (baseline - candidate) / baseline
加速比     = baseline / candidate
```

先判断主要 Bound：

| Bound | 典型证据 | 首选方向 |
| --- | --- | --- |
| Compute/Vector | 计算流水持续繁忙，搬运已覆盖 | 算法、Tile、有效计算、Reduce/融合表达 |
| GM/MTE | MTE 高或计算等待供数 | 连续搬运、片上复用、Buffer 生命周期、Double Buffer |
| Scalar | 循环、地址、Broadcast 控制占比高 | Scalar 转 Tile、模板化常量、合并控制 |
| Sync | barrier/flag 密集，C/V 或阶段等待 | owner/task 平衡、缩小同步、调整 stages |
| 并行度不足 | 活跃核少、尾波长 | task map、Tile/Core 映射、必要时 Persistent |
| 资源 | UB/L1/寄存器/Workspace 紧张 | 缩 Tile/stages、复用 Buffer、缩短生命周期 |

理想重叠可近似为：

```text
serial  ≈ copy + compute + store + sync
overlap ≈ max(copy, compute, store, sync)
```

## 2. 候选动作顺序

按收益上限和因果清晰度依次检查：

1. 算法与融合：减少无效计算、中间 GM 和 launch。
2. Tile/task map：连续访问、对齐、活跃核心、尾块、owner。
3. 数据复用：把高复用数据留在 UB/L1，合并小搬运。
4. 核内流水：从 `num_stages=2` 开始，验证真实重叠。
5. C/V 或阶段流水：先分别优化 producer/consumer，再调交接。
6. Vector 化：Tile API、Reduce、AXPY/FMA，减少 Scalar 控制。
7. Persistent/Autotune：只在任务波次和参数耦合有证据时使用。

一次只选择一个主要动作。先算容量：

```text
片上占用 ≈ Σ(Tile 元素数 × dtype 字节 × 流水版本数) + scratch
```

## 3. 症状—动作表

| 现象 | 先检查 | 候选 Plan | 风险 |
| --- | --- | --- | --- |
| C/V 时间不均 | owner、task 数、`num_stages` | 重做 owner/task map，再调 stages | 同步和 Workspace 增加 |
| Scalar 关键路径 | 行循环、Broadcast、地址分支 | Tile API、Reduce、常量化 | 改变并行粒度 |
| GM 往返频繁 | 中间值的生产者/消费者 | 延长 Tile 生命周期、阶段融合 | UB 高水位 |
| MTE 高且计算等待 | 搬运粒度、连续性、复用 | 合并 copy、Double Buffer | 预取过深 |
| 同步密集 | barrier/flag 的真实依赖 | 删除冗余同步、批量交接 | state/cache 竞态 |
| 活跃核少 | task 数和尾波 | 调整 Tile/Core、Persistent | 小 workload 调度成本 |
| pipeline 反而慢 | 气泡、资源和同步 | 分别测试 stages/Tile/sync | 多变量混改 |
| 只有单 Shape 快 | 尾块、资源和 task map | Shape 分类、Host dispatch | 版本数增长 |
| generated 临时 Tensor 多 | layout、Broadcast/Reduce lowering | 改 DSL 表达 | 后端仍生成通用路径 |

## 4. 每轮 Source Audit

每次编译后检查：

- task 数、owner 和阶段交接是否符合假设；
- UB/L1 Tile、offset、生命周期与高水位；
- `TLOAD/TSTORE` 数量和方向；
- Reduce/Broadcast 降成的目标 intrinsic；
- 新增 barrier/event 是否来自真实依赖；
- stages 增加后 Buffer/Workspace 版本数；
- JIT 与 AOT 是否使用同一 target、specialization 和 cache key。

DSL 少一次 `T.copy` 不代表设备少一次搬运。source audit 提供机制证据，msprof 提供时间证据；缺一项不判通过。

## 5. Autotune 与 Shape 分派

可搜索：

```text
Tile × K 分块 × stages × Core/task map × backend pass
```

先人工限制为合法范围，再：

- 每个候选独立跑正确性；
- 排除资源超限、尾块非法和编译失败；
- 使用相同输入和测量方法；
- 按 Shape 类别缓存最优配置；
- 保留通用 fallback；
- 不把业务主 Shape 的最优值写成全局常量。

Autotune 只搜索给定空间，不负责证明空间合理。

## 6. 切换信号

下沉 PTO 前要求：

- 公式、舍入、state、owner/task map 稳定；
- TileLang round 已收敛；
- generated source 仍有通用 Reduce/Broadcast、重复临时 Tile、state 分块或保守 event；
- Profile 指向这些残留，而非其他模型热点；
- 下一步确实需要 PTO intrinsic、UB 地址或 event 控制。

切换后保留 TileLang 作为语义、specialization 和 JIT/AOT 入口。
