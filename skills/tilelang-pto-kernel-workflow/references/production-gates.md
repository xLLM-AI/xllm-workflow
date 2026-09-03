# Production Gates

## 目录

1. Golden 与 State 合同
2. Kernel 路由与 ABI
3. Kernel A/B
4. Graph 与模型 A/B
5. 精度报告
6. 回退

## 1. Golden 与 State 合同

Golden 独立于 candidate，明确：

- 输入/输出 Shape、dtype、layout；
- 计算公式、累加 dtype 和舍入点；
- cache/state 的读取、移位、更新和写回顺序；
- 原地输出和 alias；
- `state_indices` 等动态索引；
- 典型、最小、最大、尾块和业务 Shape 类别；
- 极值、零值、正负混合；
- 连续多步 recurrent/state 测试。

分层比较中间输出。单步 final output 接近不能证明 state 正确。

## 2. Kernel 路由与 ABI

生产链逐层核对：

```text
TileLang family
  → generated PTO source
  → device object
  → op_kernel entry / tiling key
  → op_host Shape/variant dispatch
  → op_def schema
  → ACLNN
  → framework wrapper
  → Graph capture/replay
```

检查：

- target/platform/compile flags 进入 fingerprint；
- Host 只把支持的 Shape 送入 specialization；
- unsupported 场景有 fallback；
- JIT 与 AOT ABI、参数顺序和输出 alias 一致；
- OPP 实际加载本轮 object；
- Graph replay 更新动态地址与 state slot。

## 3. Kernel A/B

基线必须是用户指定的真实旧路径。若比较融合 SuperOp：

- baseline 从框架 dispatch 关闭 SuperOp；
- baseline 不得仍调用同名融合 kernel；
- split 值明确由哪些小算子 task 构成；
- candidate 值只包含新 kernel；
- Host/Runtime/Wait 是否计入必须写清。

推荐 fresh ABBA：

```text
A baseline warmup → measured
B candidate warmup → measured
B candidate fresh/warmup → measured
A baseline fresh/warmup → measured
```

按实际 harness 调整，但保持顺序对称，记录 warmup、次数、中位数和波动。新构建/OPP 后重启 fresh pair，避免旧 object 和 Graph 状态残留。

## 4. Graph 与模型 A/B

固定：

- 模型与权重；
- TP/并发；
- input/output 长度；
- eager/Graph；
- bucket capture；
- schedule overlap；
- fallback 开关；
- profiler 开关；
- 请求集与预热。

正式 TPOT 轮关闭 profiler；另采一次 trace 验证：

- 新 kernel 调用次数等于模型结构推导值；
- 旧 kernel 和 fallback 为零；
- Graph 无 eager fallback；
- capture A/replay B 只更新 B 的 state slot。

kernel speedup 不直接等于模型 speedup。模型报告注明通信、MatMul、其他算子和 overlap 仍在 TPOT 中。

## 5. 精度报告

分开写：

| 层次 | 能证明什么 | 不能证明什么 |
| --- | --- | --- |
| CPU/Golden | 公式、舍入、state 合同 | 生产 OPP/object 正确 |
| Real ATK | Host tiling、ABI、device object | 模型任务集精度 |
| Graph smoke | capture/replay 和服务可运行 | CEval 等任务精度 |
| 同配置任务 A/B | 业务任务精度 | 其他模型/配置 |

任务精度未执行时明确写“未完成”，不要用节点精度代替。

## 6. 回退

回退必须覆盖：

- framework dispatch 开关；
- Host unsupported/fallback；
- OPP/object 版本；
- Graph cache；
- 已淘汰 Plan 的代码或 feature flag。

最终验收实际执行一次回退 smoke，确认旧路径命中且输出/服务可用。
