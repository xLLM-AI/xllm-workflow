# DeepSeek-V3 优化档案

## 模型信息

| 属性 | 值 |
|------|-----|
| 参数规模 | 671B (激活 37B) |
| 架构 | MoE (Multi-Expert Mixture) |
| 专家数 | 256 (激活 8) |
| 注意力类型 | MLA (Multi-head Latent Attention) |
| 推荐卡数 | A3 x8 |
| 推荐 TP | 8 |
| 推荐 EP | 8 |

## 已知优化 (来自 xLLM PR 历史)

| PR | 优化内容 | 效果 | 状态 |
|----|---------|------|------|
| N/A | xLLM 基础 MoE 支持 | baseline | merged |
| N/A | MLA 优化 | -30% KV Cache | merged |
| N/A | EP Expert dispatch | +25% throughput | merged |

## 推荐启动命令

```bash
xllm serve /models/DeepSeek-V3 \
    --tensor-parallel-size 8 \
    --expert-parallel-size 8 \
    --graph-mode npugraph_ex \
    --block-size 128 \
    --gpu-memory-utilization 0.9
```

## 性能基线 (A3 x8)

| 指标 | Prefill | Decode (concurrent=64) |
|------|---------|----------------------|
| Throughput (tokens/s) | ~ | ~ |
| TTFT (ms) | ~ | - |
| TPOT (ms) | - | ~ |

待补充：实际 benchmark 数据

## 优化重点

### 1. Expert 负载均衡

DeepSeek-V3 的 256 个专家负载不均衡，需要：
- 动态 EPLB (Expert-Parallel Load Balancing)
- Expert 权重预加载到 SRAM

检查方式：
```bash
# 查看 expert 负载分布
# 在 profiling 中查找 MoE dispatch 相关算子
```

### 2. MLA 注意力

DeepSeek-V3 使用多头潜在注意力（MLA），KV Cache 是压缩的。

关键点：
- 确认 MLA 的 KV 压缩/解压缩 kernel 性能
- 检查量化精度是否足够

### 3. 通信优化

8 卡 EP 需要高效的 AllToAll 通信。

检查方式：
```bash
# 在 profiling 中查看 AllToAll 时长占比
# 如果 > 10%，考虑优化通信拓扑
```

## 待优化项

- [ ] EPLB 策略调优
- [ ] 通信-计算重叠优化
- [ ] Prefill 阶段的 eager/graph 混合策略

## 参考

- xLLM arXiv:2510.14686 DeepSeek-V3 相关章节
- vLLM-Ascend 的 DeepSeek 实现：`vllm_ascend/worker/`
