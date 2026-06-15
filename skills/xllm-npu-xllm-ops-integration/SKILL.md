---
name: xllm-npu-xllm-ops-integration
description: xLLM NPU xllm_ops 到 xLLM runtime 接入能力。用于 third_party/xllm_ops 中 custom op 已完成构建、wrapper 或精度验证后，把该算子接入 /opt/wqy/xllm-src-new/xllm/core/kernels/npu，补齐 xllm_ops C++ wrapper、xllm_ops_api.h 声明、CMake SRCS、上层 callsite、构建和端到端验证证据。
---

# xLLM NPU xllm_ops Runtime 接入

用于把已经存在于 `third_party/xllm_ops` 的 NPU custom op 接入 xLLM runtime，
重点路径是 `xllm/core/kernels/npu/xllm_ops` 和上层调用点。它不是从外部仓库
迁移算子源码到 `third_party/xllm_ops` 的 skill；那类任务使用
`xllm-npu-ascendc-op-migration` 或 `xllm-npu-op-migration`。

## 先读资料

- 详细接入规则：`references/xllm-ops-integration-runbook.md`
- 静态接入检查：`scripts/xllm_ops_integration_harness.py`

## 输入契约

开始前确认这些字段；缺少时先搜索仓库，不要猜：

| 字段 | 要求 |
|---|---|
| `xllm_root` | xLLM 根目录，例如 `/opt/wqy/xllm-src-new` |
| `xllm_ops_root` | `third_party/xllm_ops` 根目录 |
| `op_name` | xllm_ops 目录名或 snake_case op 名 |
| `api_symbol` | xLLM C++ wrapper 暴露给 runtime 的函数名 |
| `aclnn_name` | 底层 aclnn API 名，若 wrapper 走 `EXEC_NPU_CMD` 必填 |
| `runtime_callsite` | 需要替换或新增调用的 xLLM 层、kernel、model 或 scheduler 路径 |
| `validation_scope` | `static`、`build`、`op_accuracy`、`xllm_smoke`、`e2e_accuracy`、`performance` |

本 skill 的运行证据写入
`skills/xllm-npu-xllm-ops-integration/runs/eval/<run_id>/`。

## 工作流

### Step 1: 盘点 xllm_ops 侧状态

确认 `third_party/xllm_ops` 已具备：

- op 源码、CMake、build list；
- generated package 或 autogen header；
- Python/C++ wrapper 和单算子精度证据；
- `aclnn_name`、输入输出契约、optional/inplace 语义。

若 xllm_ops 侧还没有 build 或 accuracy 证据，先回到对应 migration skill 补齐。

### Step 2: 映射 xLLM 接入点

目标侧通常涉及：

- `xllm/core/kernels/npu/xllm_ops/<op>.cpp`：runtime C++ wrapper；
- `xllm/core/kernels/npu/xllm_ops/xllm_ops_api.h`：函数声明；
- `xllm/core/kernels/npu/xllm_ops/CMakeLists.txt`：新增 wrapper 源文件；
- 上层 runtime callsite：model/layer/kernel/sampler/cache 路径；
- build/test/eval 脚本：确保链接 `opapi`，并运行时能找到 custom OPP。

### Step 3: 实现 xLLM wrapper

wrapper 需要：

- 在 `xllm::kernel::npu` 命名空间中实现；
- 复用 `core/kernels/npu/aclnn/pytorch_npu_helper.hpp` 的 `EXEC_NPU_CMD`，除非 op 需要手动 acl tensor/list；
- 用输入 tensor 的 device/options 分配输出；
- 显式处理 dtype/layout/contiguous、optional、scalar 默认值和 inplace；
- 避免 `.cpu()`、`.item()`、`aclrtSynchronizeStream` 等 host sync，除非语义必须且报告中说明。

### Step 4: 接入 runtime callsite

接入上层时必须保留可回退路径或清楚说明替换边界：

- 固定触发条件：model、dtype、layout、decode/prefill、chunk size、shape 约束；
- fallback：unsupported shape、graph mode、optional 参数缺失时回退旧实现；
- feature flag：若项目已有开关模式，沿用现有配置风格；
- graph/replay：确认 host scalar、workspace 和 dynamic shape 不会被错误固化。

### Step 5: 验证和报告

验证顺序：

1. `python3 scripts/xllm_ops_integration_harness.py ...`
2. 最小相关 C++ build；
3. 单算子 xLLM wrapper accuracy 或现有 op accuracy 复用说明；
4. xLLM smoke：固定 prompt、确定性 sampling 或目标单元测试；
5. e2e accuracy：风险高时跑目标数据集 subset；
6. performance：带 warmup 的 before/after，不能用 profiling run 代替正式性能数据。

输出报告必须包含：

```markdown
## xllm_ops to xLLM Integration Report: <op_name>

### Source
- xllm_ops_root:
- op_name:
- aclnn_name:
- op accuracy artifact:

### Target
- xllm_root:
- wrapper:
- api header:
- CMake:
- runtime callsite:

### Interface Contract
| Arg | Shape | DType | Layout | Optional | Semantics |
|---|---|---|---|---|---|

### Validation
| Check | Command | Result | Artifact |
|---|---|---|---|

### Risks
- fallback:
- graph/dynamic shape:
- host sync:
- deployment/custom OPP:
```

如果缺少 NPU、custom OPP、模型权重或数据集导致无法验证，报告中写具体的
`integration validation blocked` 原因，不能把静态检查通过描述成 runtime 已接通。
