# Qwen3.5 GDN Decode Case

本文件是 Workflow 的案例，不是通用参数表。只有目标为同一模型契约或用户要求解释历史项目时才加载。

## 目录

1. 场景与融合边界
2. 正确性合同
3. TileLang Round 证据
4. PTO 生成与特化
5. 公平 Baseline 与结果
6. 可复用经验

## 场景与融合边界

- 模型：Qwen3.5-27B TP2
- 模型性能场景：`2048 input / 64 output`
- Graph：启用，`schedule overlap=true`
- 调用不变量：`48 layers × 64 decode tokens = 3072`
- 融合：Causal Conv1d + recurrent GDN/state + gated RMSNorm
- 边界外：Input/Output MatMul、Projection layout

模型参数：

```text
NK=8
NV=24
head_dim=128
conv_dim=5120
```

task map：

- Conv：40 个 channel owner，`40 × 128 = 5120`
- recurrent：`24 × B` 个 V-head owner
- owner 交接：GM visibility + `SyncAllAiv`

## 正确性合同

- Conv output/cache 保留 BF16 hand-off 和舍入点；
- SSM state 使用 FP32；
- state/cache 为接口副作用；
- BS1–4；
- 连续 256 recurrent steps；
- Real ATK `4/4 PASS`；
- 同配置 CEval A/B 未完成，不能表述为已通过。

## TileLang Round 证据

- TileLang UB 记录：`196,352 B`
- 预计算 `-exp(A_log)`：`+1.18%`，接受
- Gate once：`-9.50%`，回退
- recurrent + Norm 驻留 UB：延迟下降 `12.25%`，接受

这些结果说明：

- 算术量减少不保证关键路径缩短；
- 中间值留在正确 owner 的片上存储可消除 hand-off；
- 单 Shape 或单次结果不能准入。

## PTO 生成与特化

生成入口：

```python
TARGET = "pto"
tilelang.engine.lower(..., target="pto", platform="A3")
```

source specialization：

- 受检查的 `_optimize_pto_source()`；
- 两次 MatVec：`TROWEXPANDMUL + ColSum128`；
- OuterProduct：`vbrcb + vmul/vmla`；
- 拒绝残留 `TCOLEXPAND` 和通用 `TCOLSUM`；
- 显式维护 MTE2/Vector/Scalar/MTE3 依赖；
- Conv→recurrent 保留 `SyncAllAiv`。

一个 V-head 的 FP32 state：

```text
128 × 128 × 4 B = 65,536 B
```

PTO 版本让完整 state 与 compute Tile 驻留 UB，删除 half-state loop 和重复 state load/store。地址按最后一次使用复用，不能让 scratch 与仍存活 state 重叠。

## 公平 Baseline 与结果

回退：

```text
XLLM_DISABLE_QWEN35_GDN_DECODE_SUPER_OP
```

kernel baseline 是 ACLNN split 小算子链，不调用融合 `Qwen35GdnDecodeSuperOp`。

| BS | Split | PTO SuperOp | Speedup |
| ---: | ---: | ---: | ---: |
| 1 | 19.861 μs | 13.741 μs | 1.445× |
| 2 | 30.540 μs | 20.661 μs | 1.478× |
| 3 | 37.981 μs | 21.181 μs | 1.793× |
| 4 | 44.900 μs | 26.520 μs | 1.693× |

- 最差 fresh pair：`1.437×`
- 并发 1 TPOT：改善 `6.24%`
- 并发 4 TPOT：改善 `16.01%`
- PTO calls：`3072`
- old/fallback：`0`

## 可复用经验

- 用模型结构推导调用次数，比只看 kernel 名更能发现局部 fallback。
- 融合边界同时考虑 state owner、GM 往返、同步机会与框架改动面。
- TileLang 保持公式/task map/JIT/AOT 入口，PTO source 承接 intrinsic/UB/event。
- 两层都使用同一 Plan/round 证据流程。
- `SetScheduleMode(1)` 不会替代 kernel 内 ready/free 和跨流水依赖。
