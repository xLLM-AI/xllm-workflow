---
name: xllm-npu-kernel-pilot
description: xLLM NPU 算子 kernel 开发与调优 pilot，用于生成 PyTorch/torch_npu、Triton-Ascend、TileLang 或 AscendC kernel，并在 A2/A3 上验证性能。
---

# xLLM NPU 算子开发与调优 Pilot

为 xLLM 在昇腾 NPU A2/A3 上开发高性能算子 kernel，支持 PyTorch/torch_npu、
Triton-Ascend、TileLang（DSL）和 AscendC（C++）多种实现路径。

## 准入条件

kernel-pilot 仅在以下条件启动：

1. **Profiler 建议**：profiler 五表报告显示某个 kernel 族占 AICore 时间 >= 1% 且优化空间大
2. **SOTA loop 建议**：Phase 2 发现所有现成算子（torch_npu / 已有 AscendC / TileLang）均无法满足需求
3. **code-review 发现**：需要新增或替换的算子实现

## 工作流

### Step 1: 确定目标算子

**输入**：profiler kernel-table 中的热点算子

**决策**：

```
if kernel 属于已有 torch_npu 融合算子:
    → 转 benchmark 层验证，不开 kernel-pilot
elif kernel 属于已有 PyTorch / torch_npu / Triton-Ascend / TileLang 算子:
    → 转 kernel-pilot 的对应调优路径
elif kernel 是全新算子:
    → 选择实现路径: PyTorch/torch_npu / Triton-Ascend / TileLang / AscendC
```

**输出**：`op_name`，`op_type`，目标加速比，实现路径选择

### Step 2: 算子设计

#### 2.1 Shape 分析

从 kernel_details.csv 提取目标算子的典型 shape：

```python
# 示例: 从 kernel_details 中提取 MatMul shape
# shape: [batch, seq, hidden] × [hidden, ffn] → [batch, seq, ffn]
# 关注: 是否需要支持动态 seq_len, 是否有 padding
```

#### 2.2 Tiling 策略

基于目标硬件规格（A3 参考 `references/a3-specs.md`，A2/910B 参考
`references/a2-910b-specs.md`）。注意：产品页峰值只用于粗估，正式 tiling
必须通过 CANN PlatformAscendC API 和 profiling 查询当前平台资源：

| 资源 | 规格 |
|------|------|
| Core 数 | 用 `GetCoreNum()` 查询；A2/A3 分离架构下返回值需按 CANN 文档解释 |
| UB / L1 / L0 / L2 / HBM | 用 `GetCoreMemSize(CoreMemType::*)` 查询 |
| HBM 容量和带宽 | 用产品规格做粗估，用 `npu-smi info` 和 profiling 做正式记录 |
| 互联带宽 | 用产品规格做背景说明，用 HCCL/profiling artifact 判断实际瓶颈 |

Tiling 原则：
- tile_size 确保 double buffer 不超过查询得到的 UB/L1/L0 预算。
- MatMul/Cube 路径同时考虑 L1、L0A/L0B、L0C、FixPipe 和 workspace。
- Vector 路径重点考虑 UB、MTE2 load、MTE3 store 和 32B 对齐。
- `blockDim` 基于 `GetCoreNum()` 和实际 occupancy 调整，不写死为固定 core 数。

### Step 3: 实现

根据选择的路径，参考 knowledge 和 references：

- **PyTorch / torch_npu**: 参考 `kernel-pilot/knowledge/pytorch-torchnpu-patterns.md`
- **Triton-Ascend**: 参考 `kernel-pilot/knowledge/triton-ascend-patterns.md`
- **TileLang**: 参考 `kernel-pilot/knowledge/tilelang-patterns.md`
- **AscendC**: 参考 `kernel-pilot/knowledge/ascendc-patterns.md`

写入位置：
- PyTorch / torch_npu: xLLM NPU model/layer path 或 `xllm/core/layers/npu_torch/`
- Triton-Ascend: `third_party/torch_npu_ops/triton_npu/` 或框架已有 Triton-Ascend 扩展路径
- TileLang: `xllm/ops/npu/<op_name>.py` 或 `xllm/compiler/tilelang/`
- AscendC: `third_party/kernel-coding/ascendc/<op_name>/` 或 xLLM C++ 路径

### Step 4: 单元测试

```bash
# TileLang
python test/ops/npu/test_<op_name>.py --device npu

# 或运行 xllm test
python setup.py test --device npu
```

测试覆盖：
- 多种 shape（覆盖 profiling 中观察到的 shape 范围）
- fp16/bf16/fp32 多精度
- 边界情况（seq_len=1, batch_size=1 等）
- 与 reference 实现的数值对齐（atol=1e-3）

### Step 5: 基准测试

```bash
# 使用 kernel-pilot 内置工具
python kernel-pilot/tools/npu-op-benchmark.py \
    --op <op_name> \
    --shapes "128,512,4096" "1,512,4096" \
    --dtype float16 \
    --warmup 10 \
    --repeat 100

# 对比基线：
# - torch_npu 对应算子
# - 已有 AscendC/TileLang 实现
# - 纯 torch 实现
```

### Step 6: 接入 xLLM

```python
# 在 xllm/core/layers/npu_ops.py 中注册
from xllm.ops.npu import <op_name>_kernel

# 或替换已有调用
# Before:
# y = torch_npu.npu_some_op(x, weight)
# After:
y = <op_name>_kernel(x, weight)
```

### Step 7: 验证

```bash
# 单元精度
python test/ops/npu/test_<op_name>.py --device npu

# 端到端精度
python test/test_xllm_serve_generation.py --device npu

# 端到端性能
python kernel-pilot/tools/npu-op-benchmark.py --op <op_name> --report
```

## 报告格式

kernel-pilot 完成后输出：

```markdown
## Kernel Pilot Report: <op_name>

### 目标算子
- Op Type: <op_type>
- 来源: profiler kernel-table 排名 #N
- AICore time占比: X%

### 实现路径
- 选择: [TileLang | AscendC]
- 原因: <为什么选择此路径>

### Tiling 策略
- tile_M: <value>
- tile_N: <value>
- tile_K: <value>
- block_num: <value>

### 基准结果（单算子）
| 实现 | Time (us) | Speedup |
|------|-----------|---------|
| torch baseline | X | 1x |
| torch_npu | Y | X/Y x |
| 本 kernel | Z | X/Z x |

### 端到端影响
| 指标 | Before | After | Delta |
|------|--------|-------|-------|
| Throughput | ... | ... | ... |
| TTFT | ... | ... | ... |
| TPOT | ... | ... | ... |

### 精度验证
- 最大误差: <value>
- 与 reference 对齐: [Pass | Fail]
```

## 知识库与参考资料

`knowledge/` 放实现模式、cookbook 片段和调优经验，会随项目经验持续演进：

- `kernel-pilot/knowledge/pytorch-torchnpu-patterns.md` — PyTorch / torch_npu 组合算子与替换模式
- `kernel-pilot/knowledge/triton-ascend-patterns.md` — Triton-Ascend kernel 常用模式
- `kernel-pilot/knowledge/tilelang-patterns.md` — TileLang DSL 常用模式
- `kernel-pilot/knowledge/ascendc-patterns.md` — AscendC C++ 常用模式

`references/` 放硬件事实、稳定约束和 source-of-truth 规格，应只在目标平台或
支持范围变化时更新：

- `kernel-pilot/references/a3-specs.md` — Ascend A3 产品族规格
- `kernel-pilot/references/a2-910b-specs.md` — Ascend 910B / A2 规格

## 与 xllm-npu-sota-loop 的关系

kernel-pilot 是 Phase 4 的执行工具。通常由 sota-loop Phase 2（kernel-level）触发，结果回写到 sota-loop 的 attempt-ledger.md。
