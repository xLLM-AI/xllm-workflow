# Ascend A2 / 910B 硬件规格参考

> 用于 kernel-pilot 在 Atlas 300I A2、Atlas 800I A2、Atlas 800T A2
> 等 A2 系列环境上做算子设计、容量判断和性能对比。不同整机、板卡、
> firmware、CANN 版本和部署形态会影响可见资源；正式结论必须以当前机器
> `npu-smi info`、CANN PlatformAscendC API、profiling artifact 和启动日志为准。

## 适用范围

A2 不是单一芯片规格名，而是一组产品形态：

- Atlas 300I A2：PCIe 推理卡，适合单卡/多卡推理服务器集成。
- Atlas 800I A2：4U 推理服务器，采用 8 模组推理形态。
- Atlas 800T A2：4U 训练服务器。

做 kernel 或 benchmark 报告时必须写清楚产品形态和 `npu-smi info` 型号，不能只写
“A2”。

## 官方产品规格摘录

| 产品 | 官方公开规格 | kernel-pilot 关注点 |
|---|---|---|
| Atlas 300I A2 | 560 TOPS INT8，280 TFLOPS FP16；片上内存 32GB/0.8TB/s 或 64GB/1.6TB/s，支持 ECC；PCIe 5.0；最大功耗 350W | 单卡推理、算子级 benchmark、HBM 容量和带宽上界 |
| Atlas 800I A2 | 4U AI 服务器；8 模组高效推理；可选 NPU 全互联机型，整机互联带宽 392GB/s；外部网络 8 * 200GE QSFP，RoCE | 多卡推理、TP 通信、整机部署 |
| Atlas 800T A2 | 4U AI 训练服务器；8 * 200GE QSFP，RoCE；DDR4 3200MT/s 系统内存 | 训练/后训练或大模型调优场景 |

如果本地 A2 环境是 Atlas 300I A2 64GB 卡，则可用公开峰值作为粗估：

| 指标 | 数值 |
|---|---:|
| FP16 / NPU | 280 TFLOPS |
| INT8 / NPU | 560 TOPS |
| HBM / NPU | 64GB |
| HBM 带宽 / NPU | 1.6TB/s |

如果是 32GB 卡，则 HBM 带宽公开规格为 0.8TB/s。正式 MFU 或带宽利用率计算必须
写清楚使用的是 32GB 还是 64GB SKU。

## Ascend C 架构事实

官方 Ascend C 文档说明：

- Atlas A2 训练产品 / Atlas A2 推理产品采用 Cube、Vector 分离架构。
- AI Core 包含计算单元、存储单元和搬运单元。
- 存储单元包括 L1、L0A/L0B/L0C、UB、BT、FP 等。
- 搬运单元包括 MTE1、MTE2、MTE3、FixPipe。
- 存储单元大小随硬件类型变化，应通过 `GetCoreMemSize` 获取。
- 分离架构下 `GetCoreNum` 的返回含义与耦合架构不同；做 `blockDim` 前必须确认
  当前 API 返回的是哪类 core 数。

## A2 与 A3 的差异处理

| 维度 | A2 处理方式 |
|---|---|
| HBM | A2 常见 32GB/64GB SKU；A3 产品公开为 128GB/NPU。KV cache、MTP reserve、max_model_len 不可直接复用 |
| HBM 带宽 | Atlas 300I A2 64GB 为 1.6TB/s，A3 产品页公开为 3.2TB/s/NPU；memory-bound kernel 要单独复测 |
| 互联 | Atlas 800I A2 可选 NPU 全互联整机 392GB/s；A3 超节点公开 D2D 双向 784GB/s；TP/EP 通信策略需分平台验证 |
| 架构模式 | A2/A3 都属于分离架构产品范围，但 core 数和资源大小需用平台 API 查询 |
| 工具链 | Triton-Ascend、TileLang、torch_npu 支持范围可能随 CANN/Driver 改变；以当前环境为准 |

## 片上存储与 tiling 注意事项

1. 不直接复用 A3 上的 tile size 或 blockDim。
2. UB/L1/L0/L2/HBM 大小必须通过 `GetCoreMemSize` 或实际 profile 确认。
3. `blockDim` 必须基于 `GetCoreNum`，并结合 AIC/AIV 分离架构理解返回值。
4. Vector-heavy 算子优先验证 UB 容量、MTE2 load、MTE3 store 和 32B 对齐。
5. Cube-heavy 算子优先验证 L1/L0A/L0B/L0C/FixPipe 的容量、layout、fractal 和
   对齐要求。
6. A2 上出现性能低于 A3 不一定是 kernel 写错，可能是 HBM 带宽、互联、HBM 容量、
   graph 支持或 runtime 版本差异。

## Kernel Pilot 建议

| 场景 | 建议 |
|---|---|
| PyTorch / torch_npu 替换 | 先验证融合算子在 A2 当前 CANN/torch_npu 版本可用且无精度差异 |
| Triton-Ascend | 确认 runtime、二进制资产、AOT shape 和 dtype 支持 |
| TileLang | 检查 tilelang-ascend 与当前 CANN/Driver 是否匹配 |
| AscendC | 每个目标 shape 独立查询 core/memory 参数并 benchmark，不沿用 A3 常量 |
| TP 通信 | 记录是否为 NPU 全互联机型；非全互联时 TP 策略要更保守 |

## 必须记录的环境字段

- 产品形态：Atlas 300I A2 / Atlas 800I A2 / Atlas 800T A2。
- `npu-smi info` 中的 NPU 型号、HBM 容量、可见卡数。
- Driver、CANN、torch_npu、Triton-Ascend / TileLang 版本。
- `GetCoreNum`、UB/L1/L0/L2/HBM 查询值。
- 目标模型、shape、dtype、TP/PP/EP/MTP 配置。
- 单算子 benchmark、端到端 perf、profiling artifact 路径。

## 官方来源

- Huawei Enterprise: Atlas 300I A2 产品页
  `https://e.huawei.com/cn/products/computing/ascend/atlas-300i-a2`
- Huawei Enterprise: Atlas 800I A2 产品页
  `https://e.huawei.com/cn/products/computing/ascend/atlas-800i-a2`
- Huawei Enterprise: Atlas 800T A2 产品页
  `https://e.huawei.com/cn/products/computing/ascend/atlas-800t-a2`
- Ascend C: Basic Architecture
  `https://www.hiascend.com/document/detail/en/canncommercial/850/opdevg/Ascendcopdevg/atlas_ascendc_10_0008.html`
- Ascend C: GetCoreMemSize
  `https://www.hiascend.com/document/detail/en/canncommercial/850/API/ascendcopapi/atlasascendc_api_07_1034.html`
- Ascend C: GetCoreNum
  `https://www.hiascend.com/document/detail/zh/canncommercial/81RC1/apiref/ascendcopapi/atlasascendc_api_07_1028.html`
