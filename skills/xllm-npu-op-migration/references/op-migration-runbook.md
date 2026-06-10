# xLLM NPU 算子迁移 Runbook

本 runbook 总结两个算子仓库中的迁移经验：

- `https://gitcode.com/sinle4cat/torch_npu_ops`
- `https://gitcode.com/xLLM-AI/xllm_ops`

不要直接复制源文件。应从中提炼项目结构、注册模式、构建产物、验证范围和接入风险。

## 仓库模式

### torch_npu_ops

观察到的职责：

- `ops_npu/` 和 `custom_functions_npu/`：面向 ATB 和 torch_npu 的 C++ helpers。
- `ascendc_npu/`：暴露给 Python 的小型 AscendC/aclnn 示例。
- `npu_python_extension/`：用于 Python 测试的 `NpuExtension` + pybind11 注册。
- `triton_npu/`：Triton-Ascend AOT 流程；`setup.py` 运行 pytest，并把
  `.npubin` 和 json 文件收集到 binary 目录。
- 根目录 `CMakeLists.txt`：构建 `torch_npu_kernels` 和 `triton_adapter`，
  然后在 post-build 阶段运行 Triton AOT 生成。

迁移意义：

- 适合参考 PyTorch/torch_npu wrapper 和 Triton-Ascend AOT 打包方式。
- 当 xLLM 需要轻量 wrapper 或 AOT binary loading pattern 时优先参考。
- 接入 serving 前必须检查隐藏同步、cache 清理、binary path 稳定性和仅适用于测试的假设。

### xllm_ops

观察到的职责：

- `xllm_ops/<op>/op_host/`: proto, def, tiling header/source.
- `xllm_ops/<op>/op_kernel/`：AICore kernel 实现。
- `common/stub/op_api/`：用于 Python/C++ 测试的 op_api 和 Level0 stubs。
- `atb_customize/`：ATB custom operation 注册和配置。
- `test/cpp_test/`：C++ 精度/性能测试。
- `test/python_test/`：`NpuExtension`、`RegisterOps.cpp`、Python wrappers 和测试。
- 根目录构建：`bash build.sh`；CMake 支持选择 `ASCEND_COMPUTE_UNIT`
  和 operator name。

迁移意义：

- 适合参考完整 AscendC custom op 布局。
- 当算子需要 tiling、workspace、AICore kernel、生成的 aclnn/op_api entry
  或 custom ATB packaging 时优先参考。
- 必须验证 proto、def、tiling、kernel、CMake、wrapper、Python/C++ tests
  中的 op name 一致。

## 迁移决策矩阵

| 候选路径 | 优先使用条件 | 风险点 |
|---|---|---|
| PyTorch / torch_npu | 已有 aclnn/torch_npu op 足够接近且 overhead 小 | implicit sync、额外 allocation、graph capture 兼容性 |
| Triton-Ascend AOT | 中粒度融合逻辑，已有 Python Triton source，build 时能生成 binary | cache 污染、`.npubin` 命名、json/kernel name 不匹配、binary path |
| AscendC custom op | 需要确定性 tiling、workspace、自定义搬运或高 AICore 效率 | op_host/kernel contract、dynamic shape、arch specialization、package install |
| ATB customize | 需要接入 xLLM 已使用的 ATB graph/operator | parameter JSON、graph mode、padding/chunk prefill/MTP 兼容性 |

## 端到端迁移检查清单

### 1. 证据

- Baseline run 必须有 warmup。
- Profiling 明确指出具体 op family 或 host gap。
- Workload 固定：model、TP/DP、batch、input/output length、sampling params。
- 候选算子必须针对真实 xLLM 瓶颈测量，不能只看 microbenchmark。

### 2. 接口契约

记录：

- tensor shape、dtype、layout、stride 和 contiguous 要求；
- scalar 和 optional arguments；
- output allocation 和 inplace 行为；
- dynamic shape 来源，例如 `decode_step`、`actual_seq_lengths`、
  `block_table`, `num_accepted_tokens`;
- workspace 大小和生命周期；
- stream 语义，以及 wrapper 是否能避免 host synchronization。

### 3. 实现映射

典型 AscendC 映射：

```text
op_host/*_proto.cpp      -> public op schema
op_host/*_def.cpp        -> op definition and infer rules
op_host/*_tiling.*       -> tiling data and workspace decisions
op_kernel/*.cpp/.h       -> AICore implementation
CMakeLists.txt           -> register op subdirectory
RegisterOps.cpp          -> EXEC_NPU_CMD(aclnn*) wrapper for tests
xLLM callsite            -> replace old torch/aclnn/ATB path
```

典型 Triton-Ascend 映射：

```text
triton_src/*.py          -> Triton kernel and pytest reference
setup.py                 -> run pytest and copy .npubin/json
kernel_registry.*        -> load AOT binaries by kernel name
torch_api/*.cpp          -> C++ wrapper and args builder
xLLM CMake               -> build adapter and define TRITON_BINARY_PATH
```

典型 PyTorch/torch_npu 映射：

```text
NPU layer callsite       -> small wrapper around torch_npu/aclnn op
reference function       -> pure torch or existing xLLM implementation
unit test                -> deterministic random tensors on NPU
profiling check          -> verify no unexpected host sync/copy
```

## 验证等级

| 等级 | 目的 | 必要证据 |
|---|---|---|
| L1 micro accuracy | 证明数值等价 | max/mean error、失败 shape dump |
| L2 micro performance | 证明算子级收益 | warmup/repeat、p50/p90、baseline op |
| L3 xLLM smoke | 证明 serving path 可用 | 固定 prompts、确定性 sampling |
| L4 xLLM accuracy | 证明无模型精度回归 | 目标数据集 subset 或 full task |
| L5 profiling | 证明瓶颈按预期移动 | before/after kernel 和 timeline notes |

## 常见失败模式

- Wrapper 分配了错误 dtype 的 tensor，或错误地分配到 CPU。
- Optional tensor 语义与原始 op 不一致。
- Tiling 假设静态 shape，但 decode 中存在动态 `seq_len` 或 accepted tokens。
- Triton AOT binary name 与 kernel registry key 不一致。
- 源码变化后 build 仍使用旧 binary cache。
- Graph mode capture 的 shape 与 replay 时收到的 shape 不一致。
- MTP path 改变了 `num_accepted_tokens`、conv/cache position 或 padding behavior。
- 把 profiling run 当成正式性能数据。

## PR 证据规则

算子迁移 PR 应包含：

- 旧路径为什么慢或不安全；
- 选择当前算子路径为什么正确；
- 精确改动文件和影响的 runtime phase；
- 精度证据和 workload 范围；
- 带 warmup 的性能 delta；
- profiling 证据，证明预期 hotspot 已变化。
