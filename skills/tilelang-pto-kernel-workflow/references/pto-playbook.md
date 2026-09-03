# PTO-ISA Optimization Playbook

## 目录

1. 执行资源
2. 调优顺序
3. 指标—动作表
4. Buffer 与 Event 正确性
5. Generated Source Specialization
6. 验证与风险

## 1. 执行资源

| 流水 | 常见动作 | 常见问题 |
| --- | --- | --- |
| Scalar | 地址、循环、控制、取值 | Tile 太小、分支或 event 过多 |
| MTE2 | `TLOAD`，GM→UB/L1 | 供数不足、重复 load |
| MTE1 | `TEXTRACT`、布局变换 | L1→L0 变换过多 |
| Cube | `TMATMUL*` | 供数气泡或 Compute Bound |
| Vector | `TADD/TMUL/TEXP/Reduce` | 通用 Broadcast/Reduce、无效工作 |
| FixPipe | L0C 处理与写回 | 转换/输出主导 |
| MTE3 | `TSTORE`，UB→GM | 中间写回或小包多 |

总时间可分成 warm-up、steady state、drain 和同步。优先缩短稳态关键路径，同时检查小 Shape 是否被固定启动成本拖慢。

## 2. 调优顺序

1. **多核划分**：每核工作量、连续 GM 地址、尾核、HBM 争用、AIC/AIV 比例。
2. **Base Tile**：同时计算计算强度、对齐、L0/L1/UB 容量和并行 Tile 数。
3. **片上复用**：先复用，再增加并行；批量加载或 stepK 必须有容量依据。
4. **双缓冲**：明确 warm-up、steady state、drain 和 Buffer 归还。
5. **布局与中间值**：优先目标布局加载、搬运阶段转换、片上转换；最后才允许 GM 中间值。
6. **融合 intrinsic/FixPipe**：减少临时 Tile、UB pass、写回和同步点。
7. **低精度/通信**：重新规划 Scale、Buffer、消息粒度和真实拓扑。

Vector/state kernel 不必套用 Cube/stepK；根据 Profile 选择适用动作。

## 3. 指标—动作表

| 观测 | 可能原因 | 优先 Plan |
| --- | --- | --- |
| TLOAD 高、计算低 | GM/L1 供数或未重叠 | 增加复用，检查 MTE2→consumer event |
| TEXTRACT 高、Cube 低 | 布局转换重 | 目标布局、减少 Extract、增加每次计算量 |
| Vector 高、MTE 低 | 向量/归约主导 | 专用 Reduce、融合指令、删除无效工作 |
| MTE3/FixPipe 高 | 中间输出或转换主导 | 减少 GM 中间值、融合写回 |
| Scalar 高 | 小 Tile、循环/地址逻辑重 | 增大有效 Tile、常量化、简化分支 |
| 各流水都低 | 同步气泡或负载不均 | 时间线、`PIPE_ALL`、owner/Core |
| 增 Core 变慢 | 带宽/调度争用 | 降 Core，重算单核任务 |
| 小 Shape 变慢 | 流水启动成本 | 更浅 stages、更小 Tile 或独立 variant |

## 4. Buffer 与 Event 正确性

双缓冲要同时表达：

```text
producer --ready--> consumer
producer <--free--- consumer
```

- 缺 `ready`：消费者读取尚未完成的数据。
- 缺 `free`：生产者覆盖消费者仍在使用的 Buffer。
- event 复用前检查前一代依赖已结束。
- `pipe_barrier(PIPE_V)` 只约束 Vector 顺序，不能替代跨流水 event。
- 稳态 `PIPE_ALL` 会串行化所有流水，只在真实全局可见性场景使用。
- 阶段 owner 变化时明确 GM visibility 与跨核同步。

任何同步修改都跑连续 state、多轮 Buffer 复用和非零/非顺序 state index。

## 5. Generated Source Specialization

把 specialization 当作带前置条件和后置条件的编译 pass：

1. 检查 helper 插入点和目标 pattern 数量；
2. 只替换完整目标片段；
3. 插入专用 helper；
4. 检查专用调用数；
5. 拒绝残留的通用 pattern；
6. 把 target、平台、编译参数和 PTO include 写入 fingerprint/cache key；
7. 保证 JIT/AOT 从同一 kernel family 生成。

示例：

```python
source = tilelang.engine.lower(
    prim_func,
    target="pto",
    platform="A3",
)
source = _optimize_pto_source(source)
```

禁止无检查的任意字符串替换。生成结构改变时 fail closed，重新审计 transform。

## 6. 验证与风险

### 正确性

- 完整 Tile、尾 Tile、小/大 Shape、valid region、padding；
- dtype、累加与舍入；
- ready/free、event 复用、跨核可见性；
- state/cache 原地副作用；
- CPU/Golden 与 Real NPU/ATK。

### 性能

- 目标 SoC，同一频率、Core、环境和测量方法；
- 中位数和波动；
- MTE2/MTE1/Cube/Vector/FixPipe/MTE3/Scalar；
- 修改后目标流水确实变化；
- 跨 Shape 与 fresh A/B。

### 常见失败

- 只调 Base Tile，不重算单核任务和尾块；
- 只加前向依赖，没有 Buffer 归还；
- 深预取增加资源和 warm-up；
- 用 Simulator 绝对时间下结论；
- 只看总时间，不看流水和 source；
- 把一个平台/Shape 的参数写成通用最优。
