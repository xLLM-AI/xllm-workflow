# 昇腾 NPU 优化路径详细文档

## P0: 融合算子替换 (torch_npu)

### 目标

将标准 PyTorch 算子替换为 `torch_npu` 提供的融合了底层优化的算子。

### 常见替换

```python
# Attention
# Before:
attn = torch.matmul(q, k.transpose(-1, -2))
attn = torch.softmax(attn / scale, dim=-1)
out = torch.matmul(attn, v)

# After:
out = torch_npu.npu_fusion_attention(q, k, v, head_num, input_layout="BNSD")

# SwiGLU
# Before:
gate = F.silu(x)
y = gate * x_up

# After:
y = torch_npu.npu_swiglu(x)
```

### 检查方式

1. 在 profiler kernel_details.csv 中查找 `Softmax`、`Mul`、`MatMul` 等未融合的离散算子
2. 对照 npu-fuse-catalog.md 确认是否有对应的融合算子
3. 确认 torch_npu 版本支持目标算子

---

## P0: KV Cache 优化

### PagedAttention (PA)

```bash
xllm serve ... --block-size 128
```

关键点：
- block_size 影响 PA kernel 的 tiling 效率
- A3 上推荐 block_size=128 或 256
- xLLM 默认使用 PA 模式

### NZ 格式

KV Cache 使用 NZ 格式可提升 PA 性能，但转换有开销。

检查：
- 确认 KV Cache 写入和读取的 NZ 格式一致
- Prefill 和 Decode 阶段的格式对齐

### MLA 压缩

对于 DeepSeek 系列模型的多头潜在注意力（MLA），确认压缩 KV 的量化精度。

---

## P0: 图模式适配 (GE/AclGraph)

### xLLM 自适应图模式

```bash
xllm serve ... --graph-mode npugraph_ex  # Decode 阶段推荐
```

xLLM 的设计：
- Prefill 阶段：保持 eager 模式（动态 shape 友好）
- Decode 阶段：启用 npugraph_ex 或 GE 图编译

### 检查 Graph Break

在 profiler 中如果看到：
1. AICore 利用率突然降低
2. Host time 增加
3. 出现 AICPU 算子

可能是某个算子/shape 不支持图编译导致 graph break。

检查方式：
```bash
# 查看 GE 编译日志
grep -r "not supported\|fallback\|graph break" /path/to/ge_logs/
```

---

## P1: 权重预取 (npu_prefetch)

### 原理

在计算当前层时，提前将下一层的权重从 Global Memory 加载到 SRAM/UB。

### 使用方式

```python
import torch_npu

# 在模型 forward 中注册 prefetch
torch_npu.npu_prefetch(
    weight,       # 下一层的权重 tensor
    current_op,   # 当前正在执行的操作
    0,            # offset
    weight_size   # 数据大小
)
```

### 检查方式

在 profiler 中观察：
- 权重加载时间是否隐藏在当前计算中
- MTE 时间与 AICore 时间的重叠率

---

## P1: 多流重叠 (stream overlap)

### 计算-通信双流

```python
import torch_npu

# 在独立 stream 上执行通信
comm_stream = torch.npu.Stream()
with torch.npu.stream(comm_stream):
    torch.distributed.all_reduce(tensor)
```

### 适用场景

- Tensor Parallel 的 AllReduce
- Expert Parallel 的 AllGather/AllToAll
- Pipeline Parallel 的 P2P 通信

---

## P1: 并行策略 (TP/EP/DP)

### 推荐配置（A3 x4/x8）

| 模型 | TP | EP | PP | 说明 |
|------|----|----|----|----|
| Qwen3-32B | 4 | - | - | Dense, TP-only |
| DeepSeek-V3 | 8 | 8 | - | MoE, TP+EP |
| Qwen3-235B | 8 | 8 | - | MoE, TP+EP |
| Kimi-k2 | 8 | 8 | - | MoE, TP+EP |

---

## P2: 通信优化 (HCCL)

### AllReduce 拓扑

```bash
# 检查拓扑
npu-smi info -t topo

# 确认 ROCE 配置
hccl_info --device
```

### 通信-计算重叠率

在 step_trace_time.csv 中：
- 通信时间占比 > 10% 时考虑优化
- 检查是否已有通信重叠
- 检查 NCCL/HCCL 算法选择

---

## P2: 投机解码

### Draft Model 选择

```bash
xllm serve ... --speculative-model /path/to/draft \
  --speculative-num-steps 4 \
  --speculative-eagle-topk 2 \
  --speculative-num-draft-tokens 8
```

适用场景：
- 输出长序列（>512 tokens）
- Draft model 与 target 分布接近

---

## P2: MoE 动态 EPLB

### Expert-Parallel 负载均衡

```bash
xllm serve ... --eplb-strategy dynamic
```

在 DeepSeek-V3、Qwen3-235B 等 MoE 模型上，动态 EPLB 可减少 TP imbalance。
