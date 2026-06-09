# NPU 重叠机会目录

## 概述

本目录列出昇腾 NPU 910B3 上可用的计算-通信重叠机会，用于 Profiling 五表报告的 Overlap-Opportunity Table。

## 计算-通信重叠

| 重叠模式 | 计算侧 | 通信侧 | 场景 | 来源 |
|---------|--------|--------|------|------|
| MatMul + AllReduce | MoE Gate MatMul | 专家路由 AllGather | MoE forward | torch_npu |
| QKV MatMul + TP AllGather | Next Layer QKV | 上一层 TP AllReduce | Tensor Parallel | HCCL |
| FFN Compute + TP Comm | FFN intermediate | TP AllReduce | Transformer 层 | HCCL |
| Expert Compute + EP AllToAll | 非本 rank Expert | Expert 权重 AllGather | Expert Parallel | HCCL |

## 计算-计算重叠

| 重叠模式 | 主流 | 从流 | 场景 | 来源 |
|---------|------|------|------|------|
| MTE3 + AICore | 数据搬运 (MTE3) | 计算 (AICore) | 所有算子 | 硬件双流水 |
| MTE2 + AICore | AICore→UB→L1 搬运 | AICore 计算 | 所有算子 | 硬件双流水 |
| Decode batch + Prefill | Decode tokens | 下一 Prefill 请求 | 混合调度 | xLLM |

## 内存-计算重叠

| 重叠模式 | 说明 | 来源 |
|---------|------|------|
| KV Cache 分配 + 当前 batch | 异步分配下一 batch 的 KV block | xLLM |
| PagedAttention block fetch + compute | 异步加载下一个 block | xLLM |
| 权重预取 (npu_prefetch) | 提前加载下一层权重到 SRAM | CANN |
| xTensor async alloc | 异步内存池分配 | xLLM |

## 如何识别重叠机会

### 从 Profiling 数据

1. 查看 `step_trace_time.csv` 中的 step 时间分布
2. 比较 AICore 活跃时间与总 step 时间的比例
3. 如果 AICore 利用率低但算子时间已优化，检查是否有重叠机会

### 从代码

1. 检查是否有多流（MTE3/AICore/AICPU 分派）
2. 检查通信是否在独立 stream
3. 检查是否有 `npu_prefetch` 注册
4. 检查 MoE/TP 通信是否与计算重叠

### xLLM 特化

xLLM 的三层异步流水线编排（请求调度 + 模型图 + 算子）天然支持以下重叠：
- 请求调度层与模型执行层的流水线重叠
- 图模式的编译缓存与执行重叠
- PD 分离后 Prefill 和 Decode 的独立调度
