# NPU 融合算子目录

## 概述

本目录列出昇腾 NPU 910B3 上可用的融合算子模式，用于 Profiling 五表报告的 Fuse-Pattern Table 确定性匹配。

所有融合模式均基于代码源匹配（source-backed），不使用模糊匹配。

## 确定性融合模式

### Attention 相关

| 模式 | 融合前 | 融合后 | 来源 | 适用框架 |
|------|--------|--------|------|---------|
| FlashAttention | QKV→Scale→Mask→Softmax→Dropout→V | `torch_npu.npu_fusion_attention` | torch_npu | xLLM, vLLM |
| PagedAttention | block gather + attention | `torch_npu.npu_paged_attention` | torch_npu | xLLM, vLLM |
| MLA (Multi-head Latent Attention) | KV compress + attention + dequant | custom MLA kernel | xLLM | xLLM |

### MatMul 相关

| 模式 | 融合前 | 融合后 | 来源 | 适用框架 |
|------|--------|--------|------|---------|
| MatMul+Add+Bias | MatMul → Add → BiasAdd | MatMul + BiasAdd 融合 | CANN CCE | 所有 |
| MatMul+GeLU | MatMul → GeLU | `torch_npu.npu_matmul_act` | torch_npu | xLLM, vLLM |
| MatMul+SiLU | MatMul → SiLU | `torch_npu.npu_matmul_act` (silu) | torch_npu | xLLM, vLLM |

### Normalization

| 模式 | 融合前 | 融合后 | 来源 | 适用框架 |
|------|--------|--------|------|---------|
| RMSNorm+Add | RMSNorm → Add | `torch_npu.npu_rms_norm` (fused add) | torch_npu | xLLM, vLLM |
| LayerNorm+Add | LayerNorm → Add | `torch_npu.npu_layer_norm` (fused) | torch_npu | xLLM, vLLM |

### Element-wise

| 模式 | 融合前 | 融合后 | 来源 | 适用框架 |
|------|--------|--------|------|---------|
| SiLU+Mul | SiLU → Mul (SwiGLU) | `torch_npu.npu_swiglu` | torch_npu | xLLM, vLLM |
| GeGLU | GeLU → Mul | `torch_npu.npu_geglu` | torch_npu | xLLM, vLLM |
| Add+Mul | Add → Mul (residual) | 自定义 AscendC kernel | xLLM | xLLM |

### MoE 相关

| 模式 | 融合前 | 融合后 | 来源 | 适用框架 |
|------|--------|--------|------|---------|
| Expert dispatch | Gate → topk → scatter → MatMul → gather | MoE dispatch kernel | xLLM | xLLM |
| Expert combine | MatMul → gather → reduce | MoE combine kernel | xLLM | xLLM |

## xLLM 独有优化

| 模式 | 说明 | 检查方式 |
|------|------|---------|
| 自适应图模式 | Prefill eager + Decode npugraph_ex/GE | 检查 graph_mode 配置 |
| npu_prefetch | 权重预取到 SRAM | 检查模型是否使用了 prefetch 注册 |
| SuperKernel | 算子二进制融合（GE 优化） | 检查 graph_mode 是否为 ge |

## 使用方式

在 Profiling 分析时，将 kernel_details 中的算子名称与本目录的 "融合前" 列表进行匹配。如果某个可融合的算子模式未被匹配，说明融合优化未生效。
