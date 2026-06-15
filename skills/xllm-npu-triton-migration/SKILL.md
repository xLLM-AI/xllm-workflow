---
name: xllm-npu-triton-migration
description: xLLM NPU Triton-Ascend 算子迁移能力。用于将 vLLM-Ascend、实验目录或外部仓库中的 Triton 自定义算子迁移到 torch_npu_ops/xLLM AOT 形态，补齐 Python Triton kernel、pytest 精度验证、单一 .npubin AOT 产物、C++ torch API wrapper、OperationFactory、CMake、GTest 和验证证据。
---

# xLLM NPU Triton-Ascend 算子迁移

用于把 Triton-Ascend 自定义算子迁移成 xLLM/torch_npu_ops 可构建、可测试、
可复查的 AOT 算子。源 skill 迁移自
`/opt/wqy/jd/skills/triton_migration_skill.md`，并按当前 `xllm-workflow/skills`
目录结构整理。

## 先读资料

- 标准迁移流程：`references/triton-migration-runbook.md`
- 原始迁移参考：`references/triton-migration-original-reference.md`。当需要查看
  `rope_inplace` 完整接入示例、ATB Triton 接入 demo、问题记录、ttir 参数排查
  或 debug 辅助函数时读取。
- 若需要把迁移后的算子进一步接入 xLLM runtime：使用
  `xllm-npu-xllm-ops-integration`
- 若还在 PyTorch/torch_npu、Triton-Ascend、AscendC 之间选型：先根据
  `AGENTS.md` 的 skill routing 和目标仓本地规则选择最窄入口；本 skill 只覆盖
  Triton-Ascend AOT 迁移。

## 输入契约

开始前确认这些字段；缺少时先搜索代码，不要猜：

| 字段 | 要求 |
|---|---|
| `source_repo` | vLLM-Ascend、实验路径或外部仓库 |
| `target_repo` | `torch_npu_ops` 或承载 Triton AOT 的 xLLM 目标仓 |
| `op_name` | Python wrapper/C++ API 名基础 |
| `kernel_name` | Triton kernel 名，必须和 AOT binary 注册名一致 |
| `source_kernel` | 原 Triton kernel 文件和入口 |
| `runtime_params` | batch、heads、tokens 等运行时变化参数 |
| `constexpr_params` | `tl.arange`、tile size、head dim 等编译期常量 |
| `validation_scope` | `python_accuracy`、`aot_build`、`cpp_gtest`、`xllm_smoke`、`performance` |

## 工作流

### Step 1: 盘点源 Triton kernel

输出迁移表：

| 项 | 内容 |
|---|---|
| kernel | 原入口、grid、block/tile 参数 |
| inputs/outputs | shape、dtype、layout、stride、contiguous |
| dynamic params | 运行时变化且不能 specialization 的参数 |
| constexpr params | 编译期常量和来源 |
| reference | PyTorch/CPU reference 或已有 golden |
| workload | 对应 xLLM/vLLM 场景和典型 shape |

### Step 2: 改造 Python Triton + pytest

在 `triton_npu/triton_src/test_<op_name>.py` 中同时保留 kernel、Python wrapper
和 pytest。

必须检查：

- 所有运行时变化参数用 `@triton.jit(do_not_specialize=[...])` 标记；
- `tl.arange(0, N)` 的 `N` 只来自 `tl.constexpr`；
- 遍历运行时变量时用 `tl.range`，不要用 `tl.static_range`；
- pytest 覆盖至少 2-3 个典型 shape；
- pytest 直接对比 reference，输出或断言明确的 `atol/rtol/max_abs`。

### Step 3: 生成 AOT 单一 binary

运行 `triton_npu/setup.py` 或目标仓等价入口，要求：

- pytest 通过；
- AOT 只生成一个 unique kernel；
- `<kernel_name>.npubin` 和 json 复制到目标 `binary/` 目录；
- 不把多 shape specialization 误生成多个 binary。

### Step 4: 接入 C++ torch API

补齐目标文件：

- `triton_npu/torch_api/operations.h`：新增 `OperationBase` 派生类；
- `triton_npu/torch_api/operation_factory.h`：新增工厂方法；
- `triton_npu/torch_api/triton_ops_api.h`：新增 C++ API 声明；
- `triton_npu/torch_api/npu_triton_<op_name>.cpp`：实现 wrapper 和 ArgsBuilder；
- `CMakeLists.txt`：加入 `TRITON_NPU_API_SRCS`；
- `triton_npu/test/CMakeLists.txt`：加入 GTest target。

wrapper 要求：

- `ArgsBuilder::constructArgs(...)` 顺序必须和 Triton kernel 签名完全一致；
- Vector Core Triton 算子优先查询 `ACL_DEV_ATTR_VECTOR_CORE_NUM`；
- 不在 wrapper 热路径增加 `.cpu()`、`.item()` 或隐式 stream sync；
- 所有 output 使用输入 tensor 的 device/options 分配。

### Step 5: C++ GTest 和验证闭环

至少运行：

```bash
cd <target_repo>/triton_npu
python3 setup.py

cd <build_dir>
cmake ..
make -j triton_adapter
make -j <op_name>_test
./triton_npu/test/<op_name>_test
```

如果目标仓构建入口不同，沿用项目已有 build 命令，不新造脚本。

## 报告模板

```markdown
## Triton-Ascend Op Migration Report: <op_name>

### Source
- source_repo:
- source_kernel:
- op_name:
- kernel_name:

### Target
- target_repo:
- triton_src:
- torch_api wrapper:
- CMake:
- GTest:
- binary:

### Interface Contract
| Arg | Shape | DType | Layout | Runtime/Constexpr | Semantics |
|---|---|---|---|---|---|

### Validation
| Check | Command | Result | Artifact |
|---|---|---|---|

### Risks
- AOT specialization:
- constexpr/runtime split:
- vector core grid:
- xLLM runtime integration:
```

若缺少 Triton-Ascend 环境、NPU、torch_npu、CANN 或构建依赖，报告中写
`triton migration validation blocked`，不能把静态接入描述成构建或精度通过。
