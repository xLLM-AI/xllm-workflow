# Ascend A3 硬件规格参考

> 用于 kernel-pilot 在 Atlas 800I A3 / Atlas 800T A3 / Atlas 900 A3
> 等 A3 系列环境上做算子设计、tiling 约束和性能上界估算。正式结论必须以
> 当前机器 `npu-smi info`、CANN PlatformAscendC API、profiling artifact
> 和启动日志为准。

## 适用范围和命名

华为公开产品页通常以 **Atlas 800I A3 / Atlas 800T A3** 或 **昇腾910**
描述产品规格；本仓库历史上把本地设备称为 **910B3 / A3**。写报告时建议同时记录：

- 产品形态：Atlas 800I A3、Atlas 800T A3、Atlas 900 A3 SuperPoD 等。
- `npu-smi info` 看到的芯片/板卡型号。
- CANN / Driver / firmware 版本。
- 每张卡的 HBM、带宽、可见 device id、互联拓扑。

不要仅凭“A3”二字推导所有 kernel 参数。

## 官方产品规格摘录

| 产品 | NPU | 片上内存 | AI 算力 | D2D/互联 | 典型场景 |
|---|---|---:|---:|---:|---|
| Atlas 800I A3 | 单机 8 * 昇腾910，最大 384 卡超节点 | 8 * 128GB，内存带宽 3.2TB/s | 最大 4.48 PFLOPS FP16，8.96 POPS INT8 | 双向 784GB/s | 大模型推理 |
| Atlas 800T A3 | 单机 8 * 昇腾910，最大 384 卡超节点 | 8 * 128GB，内存带宽 3.2TB/s | 最大 6.0 PFLOPS FP16，12.0 POPS INT8 | 双向 784GB/s | 预训练 / 后训练 |
| Atlas 900 A3 SuperPoD | 最大 384 * 昇腾910 | 最大 384 * 128GB，带宽速率最大 3.2TB/s | 最大 307.2 / 288.7 PFLOPS@FP16 | D2D 双向 784GB/s，约 200ns 单跳时延 | 超节点集群 |

按 8 NPU 单机口径粗略折算：

| 产品 | FP16 / NPU | INT8 / NPU | HBM / NPU | HBM 带宽 / NPU |
|---|---:|---:|---:|---:|
| Atlas 800I A3 | 约 560 TFLOPS | 约 1.12 POPS | 128GB | 3.2TB/s |
| Atlas 800T A3 | 约 750 TFLOPS | 约 1.5 POPS | 128GB | 3.2TB/s |

注意：上表是从整机公开规格除以 8 得到的产品级估算，用于容量规划、MFU
粗估和 benchmark 背景说明；kernel 报告中的正式 peak 值必须记录来源。

## Ascend C 架构事实

官方 Ascend C 文档说明：

- A3 训练 / 推理产品采用 Cube、Vector 分离架构。
- AI Core 负责 Cube 和 Vector 密集计算，包含 Cube Unit、Vector Unit、
  Scalar Unit。
- 片上存储包含 L1 Buffer、L0A/L0B/L0C Buffer、Unified Buffer、BiasTable
  Buffer、FixPipe Buffer。
- 搬运单元包含 MTE1、MTE2、MTE3 和 FixPipe。
- 存储单元大小随 AI 处理器类型变化，应通过 `GetCoreMemSize` 获取。
- 核数应通过 `GetCoreNum` 或 profiler 获取；分离架构下返回值可能对应
  Vector 核数量，不能直接等同于旧文档里的“AI Core 数”。

## 片上存储与搬运路径

| 资源 | 作用 | kernel-pilot 使用建议 |
|---|---|---|
| GM / HBM | 全局内存；模型权重、KV cache、输入输出 tensor | 记录 HBM 容量和带宽，结合 NPU utilization / memory bandwidth 判断是否 memory-bound |
| L2 Cache | GM 访问缓存，cacheline 大小随硬件规格变化 | 不写死 cacheline；从 profiling 和 CANN 文档确认 |
| L1 Buffer | Cube 复用数据的片上缓冲 | MatMul/Conv tiling 要评估 L1 reuse 和 MTE2 带宽 |
| L0A / L0B | Cube 指令输入 | 关注 16x16 cube、fractal/layout 和 512B 对齐 |
| L0C | Cube 输出和累加中间结果 | 关注 accumulation、FixPipe、类型转换和回写 |
| UB | Vector / Scalar 输入输出 | elementwise、softmax、postprocess、copy/fill 的核心约束 |
| MTE1 | L1 -> L0A/L0B、L1 -> BT 等 | 设计 L1 到 Cube 输入的流水 |
| MTE2 | GM -> L1/L0A/L0B、GM -> UB | load 路径，满足 cacheline 对齐通常更高效 |
| MTE3 | UB -> GM | vector 结果回写路径 |
| FixPipe | L0C -> GM/L1，随路类型/格式转换 | MatMul 后处理、量化、激活融合时重点看 |

## 必须动态查询的硬件参数

这些值不要写死到 kernel 或 reference 结论中：

| 参数 | 获取方式 | 用途 |
|---|---|---|
| AIC/AIV/Core 数 | `PlatformAscendC::GetCoreNum()`、profiling、`npu-smi info` | `blockDim`、并行切分、occupancy |
| UB/L1/L0/L2/HBM 大小 | `PlatformAscendC::GetCoreMemSize(CoreMemType::*)` | tile size、double buffer、workspace |
| HBM 可用容量 | `npu-smi info`、启动日志、框架 memory planner | KV cache、max batch、MTP reserve |
| 实际带宽和互联拓扑 | profiling、HCCL 日志、NPU 拓扑工具 | TP/EP 通信、AllReduce/AllGather |
| dtype 支持与 layout 限制 | CANN/torch_npu/Triton-Ascend 当前版本文档和测试 | kernel 选型和 fallback |

示例：

```cpp
auto platform = platform_ascendc::PlatformAscendC(context->GetPlatformInfo());
auto core_num = platform.GetCoreNum();

uint64_t ub_size = 0;
uint64_t l1_size = 0;
platform.GetCoreMemSize(platform_ascendc::CoreMemType::UB, ub_size);
platform.GetCoreMemSize(platform_ascendc::CoreMemType::L1, l1_size);

context->SetBlockDim(core_num);
```

## Tiling 约束

### 基本原则

1. **先查平台参数**：使用 `GetCoreNum` / `GetCoreMemSize` 生成或选择 profile。
2. **不要假设 UB=2MB**：历史经验可作为初始猜测，正式 tiling 必须以平台 API
   返回值为准。
3. **Vector 路径关注 UB**：`GM -> UB -> Vector -> UB -> GM`，尽量减少多次
   GM 往返和 host 下发。
4. **Cube 路径关注 L1/L0/FixPipe**：`GM -> L1 -> L0A/L0B -> Cube -> L0C
   -> FixPipe -> GM/L1`。
5. **对齐优先**：UB/L1 起始地址通常至少 32B 对齐；L0A/L0B 和 L0C 有更严格
   对齐要求，具体以当前 CANN API 约束为准。
6. **通信不只看 HCCL kernel 时间**：A3 超节点 D2D 带宽高，但 decode 场景仍可能
   被 host 下发、同步、shape copy 或 HCCL wait 间接拖慢。

### MatMul 初始估算

```text
tile_bytes =
  bytes(A_tile in L1/L0A)
+ bytes(B_tile in L1/L0B)
+ bytes(C_tile in L0C or output staging)
+ bytes(double-buffer reserve)
+ bytes(alignment / workspace reserve)

要求：tile_bytes < queried_local_memory_budget
```

`queried_local_memory_budget` 必须来自 `GetCoreMemSize` 或运行时 profile，而不是写死常量。

## LLM 推理关注点

| 场景 | A3 关注点 |
|---|---|
| 长序列 prefill | HBM 带宽、MatMul/Cube 利用率、attention layout、chunk prefill |
| decode | hostbound gap、graph replay 参数准备、small batch kernel launch、postprocess |
| MTP / speculative | draft/verify 一致性、KV cache 位置、接受率、draft 下发重叠 |
| TP/EP 通信 | HCCL wait、D2D 拓扑、AllReduce/AllGather 与计算重叠 |
| 算子迁移 | graph 模式、动态 shape、fallback、dtype/layout、workspace |

## 官方来源

- Huawei Enterprise: Atlas 800I A3 产品页
  `https://e.huawei.com/cn/products/computing/ascend/atlas-800i-a3`
- Huawei Enterprise: Atlas 800T A3 产品页
  `https://e.huawei.com/cn/products/computing/ascend/atlas-800t-a3`
- Huawei Enterprise: Atlas 900 A3 SuperPoD 产品页
  `https://e.huawei.com/cn/products/computing/ascend/atlas-900-a3-superpod`
- Ascend C: Basic Architecture
  `https://www.hiascend.com/document/detail/en/canncommercial/850/opdevg/Ascendcopdevg/atlas_ascendc_10_0008.html`
- Ascend C: GetCoreMemSize
  `https://www.hiascend.com/document/detail/en/canncommercial/850/API/ascendcopapi/atlasascendc_api_07_1034.html`
- Ascend C: GetCoreNum
  `https://www.hiascend.com/document/detail/zh/canncommercial/81RC1/apiref/ascendcopapi/atlasascendc_api_07_1028.html`
