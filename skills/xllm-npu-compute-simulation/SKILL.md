---
name: xllm-npu-compute-simulation
description: LLM serving 的 NPU 计算量模拟。用于判断 kernel 是否接近硬件上限、估算 FLOPs/MFU、估算 prefill/decode 计算成本，或为 xLLM、vLLM-Ascend、SGLang 在 Ascend NPU 上做 TP/EP/MTP shape what-if 分析。
---

# xLLM NPU 计算量模拟

用于估算理论计算成本，并把 profiling 时间与硬件下界进行对比。

## 输入

- 模型配置：layers、hidden size、intermediate size、attention heads、
  KV heads、vocab size，以及 MoE 配置。
- Serving shape：batch、input tokens、output tokens、TP/PP/EP、dtype。
- 可用时提供 profiling kernel table。
- NPU 规格来自 [`../../references/npu-specs.json`](../../references/npu-specs.json)。

## 工作流

1. 按算子族估算 prefill 和 decode FLOPs：
   attention、MLP、projection、embedding/lm_head、MoE、recurrent/state modules。
2. 按并行策略修正：TP/PP/EP 与通信开销分开计算。
3. 根据 NPU 峰值吞吐和 dtype 计算硬件下界时间。
4. 对比 profiling device time 和理论时间：

   ```text
   MFU = estimated_flops / (elapsed_seconds * peak_flops)
   ```

5. 归类差距：compute-bound、memory-bound、communication-bound、hostbound 或 unknown。
6. 对安全参数变更给出 what-if 估算，例如 TP、MTP depth、batch size 或 output length。

## 输出

```text
runs/compute/<run_id>/
  manifest.md
  compute-estimate.json
  mfu-table.md
  what-if.md
```

## 规则

- 未经 profiling 校准前，所有估算只作为方向性判断。
- 不要在未记录实际 token 数的情况下比较 tokenizer/template 输出长度不同的模型。
- 如果模型配置不完整，明确标出缺失项，不要自行编造数值。

## 参考资料

- [`../../references/npu-specs.json`](../../references/npu-specs.json)
- [`../../references/model-config-index.json`](../../references/model-config-index.json)
- [`references/llm-flops-formulas.md`](references/llm-flops-formulas.md)
