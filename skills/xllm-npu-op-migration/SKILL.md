---
name: xllm-npu-op-migration
description: xLLM NPU 算子迁移与接入流程。用于分析 torch_npu_ops、xllm_ops、PyTorch/torch_npu、Triton-Ascend、AscendC 自定义算子，并将候选算子迁移到 xLLM 的 CMake、op_host、op_kernel、EXEC_NPU_CMD、Python/C++ wrapper 和端到端验证闭环。
---

# xLLM NPU 算子迁移

用于把外部或实验性 NPU 算子迁移到 xLLM，并留下可复查的精度、性能和
profiling 证据。

## 先读哪些资料

- 迁移流程和参考仓库差异：`references/op-migration-runbook.md`
- 如果是 Triton-Ascend：再读 `kernel-pilot/knowledge/triton-ascend-patterns.md`
- 如果是 PyTorch / torch_npu：再读 `kernel-pilot/knowledge/pytorch-torchnpu-patterns.md`
- 如果是 AscendC：再读 `kernel-pilot/knowledge/ascendc-patterns.md`

## 适用场景

使用本 skill 当：

1. profiling 证明某个后处理、cache、attention、MoE 或 Mamba/SSM 算子是瓶颈；
2. 已有外部算子仓库实现可借鉴，需要迁移到 xLLM；
3. 需要在 PyTorch/torch_npu、Triton-Ascend AOT、AscendC custom op 之间选型；
4. 需要把算子接入 xLLM 的 C++/Python wrapper、CMake、UT、性能和 profiling。

不使用本 skill 当：

- 只是单纯写一个新 kernel，且没有迁移/接入问题：使用 `kernel-pilot`。
- 只是评测性能：使用 `xllm-npu-eval-runner` 或 `xllm-npu-benchmark`。
- 只是定位精度：使用 `xllm-npu-accuracy-debug`。

## 迁移流程

### Step 1: 源算子盘点

先输出候选算子的来源表：

| 字段 | 要求 |
|---|---|
| source repo | 外部仓库、xLLM 分支或本地实验路径 |
| op name | Python 名、aclnn 名、kernel 名分别列出 |
| source mode | PyTorch/torch_npu、Triton-Ascend、AscendC、ATB customize |
| workload | prefill/decode、batch、seq、hidden、dtype、layout |
| evidence | baseline 性能、profiling hotspot、端到端痛点 |

### Step 2: 接口与 shape 对齐

迁移前必须写清：

- 输入/输出 tensor：shape、dtype、layout、是否 contiguous；
- 标量参数：int、float、bool、optional tensor 的默认语义；
- 动态 shape：decode step、actual seq len、block table、workspace 是否变化；
- inplace 语义：输入是否被改写，输出是否 alias；
- stream 语义：是否依赖当前 stream、是否有 host sync、是否需要 event。

### Step 3: 选择实现路径

按这个顺序决策：

```text
已有 torch_npu/aclnn 能表达且性能足够
  -> PyTorch / torch_npu wrapper
已有 Triton-Ascend 实现或算子适合小/中粒度融合
  -> Triton-Ascend AOT
需要 op_host tiling、workspace、AICore kernel 或自定义 aclnn 接口
  -> AscendC custom op
需要 ATB graph/operator 组合且 xLLM 已有 ATB 接口
  -> ATB customize
```

选择结果必须说明为什么不用更简单路径。

### Step 4: xLLM 接入

按选型接入：

| 路径 | 接入点 | 注意事项 |
|---|---|---|
| PyTorch / torch_npu | xLLM NPU layer/model path 或小 wrapper | 避免隐式 `.cpu()`、`.item()`、同步 copy |
| Triton-Ascend | AOT binary 生成、kernel registry、C++ API wrapper | 固定 `TRITON_BINARY_PATH`，构建时生成 `.npubin`/json |
| AscendC | `op_host`、`op_kernel`、CMake、aclnn/op_api、wrapper | proto/def/tiling/kernel 名称一致 |
| ATB customize | ATB operation wrapper、参数 JSON、graph 配置 | 确认 graph/pad/chunk prefill/MTP 路径兼容 |

### Step 5: 验证闭环

每个迁移 PR 至少给出：

1. 单算子 reference 对齐：覆盖 profiling 里的典型 shape；
2. 端到端精度：至少 L2，风险高时升到目标数据集 task；
3. 性能：带 warmup 的 baseline/current，不能用 profiling run 直接下结论；
4. profiling：证明热点或 host gap 变化符合预期；
5. 回写：把踩坑、shape、收益、失败路径写回对应 skill 或 history。

## 输出模板

```markdown
## xLLM NPU Op Migration Report: <op>

### 来源与目标
- Source repo:
- Source mode:
- Target xLLM path:
- Workload:
- Profiling evidence:

### 接口对齐
| Arg | Shape | DType | Layout | Semantics |
|---|---|---|---|---|

### 实现路径
- Chosen:
- Rejected alternatives:
- Build artifacts:

### 接入点
- CMake:
- op_host / op_kernel:
- EXEC_NPU_CMD / wrapper:
- xLLM callsite:

### 验证
| Check | Baseline | Current | Result |
|---|---|---|---|
| op accuracy | | | |
| e2e accuracy | | | |
| TPOT/TTFT/TPS | | | |
| profiling hotspot | | | |

### 风险
- Graph mode:
- Dynamic shape:
- MTP/speculative:
- Memory/workspace:
```
