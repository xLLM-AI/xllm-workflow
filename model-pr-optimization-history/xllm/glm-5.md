# GLM-5 优化档案

## 模型信息

| 属性 | 值 |
|------|-----|
| 架构 | 类 GPT (ChatGLM style) |
| 参数规模 | 待确认 |
| 注意力类型 | GQA (Grouped Query Attention) |
| 激活函数 | SwiGLU |
| 位置编码 | RoPE |
| 推荐卡数 | A3 x4 (根据实际规模) |
| 推荐 TP | 4 |

## 推荐启动命令

```bash
xllm serve /models/GLM-5 \
    --tensor-parallel-size 4 \
    --graph-mode npugraph_ex \
    --block-size 128 \
    --gpu-memory-utilization 0.9
```

## 性能基线 (待测)

| 指标 | Prefill | Decode (concurrent=64) |
|------|---------|----------------------|
| Throughput (tokens/s) | ~ | ~ |
| TTFT (ms) | ~ | - |
| TPOT (ms) | - | ~ |

## 已知优化

| 优化项 | 效果 | 状态 |
|--------|------|------|
| 标准 Transformer 支持 | baseline | merged |
| PagedAttention | KV Cache 高效管理 | merged |

## 优化重点

### 1. 架构适配

GLM-5 可能有一些与标准 Llama 不同的架构特点：
- 自定义 attention mask
- 特殊的 tokenization

检查方式：
- 查看模型 config 中的特殊配置
- 对比 xLLM 的 GLM 实现与原始实现

### 2. 图模式兼容性

确认 GLM-5 的特殊算子在 npugraph_ex 下能正确编译。

### 3. 精度对齐

首次支持 GLM-5 时需要与 GPU 版本进行精度对齐。

## 待优化项

- [ ] 确认模型架构兼容性
- [ ] 图模式适配验证
- [ ] 精度对齐测试
- [ ] 端到端性能 benchmark

## 参考

- xLLM GLM 相关代码：`xllm/core/models/`
- vLLM-Ascend GLM 实现：`vllm_ascend/model_executor/models/`
