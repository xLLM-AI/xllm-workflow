# xllm_ops 接入 xLLM Runtime Runbook

本 runbook 面向“算子已经在 `third_party/xllm_ops` 中存在”的场景，目标是把它接入
`xllm/core/kernels/npu`，并在 xLLM serving 路径中可控地调用。

## 目标布局

常见目标结构：

```text
xllm/core/kernels/npu/
  xllm_ops/
    CMakeLists.txt
    xllm_ops_api.h
    <op>.cpp
  aclnn/
    pytorch_npu_helper.hpp
```

`xllm_ops/CMakeLists.txt` 一般构建 `xllm_ops` cc library，依赖 `opapi`、
`torch_npu`、`atb`、`gflags` 等。新增 wrapper 时优先沿用已有 `cc_library`
模式，只增加必要源文件。

## 接入清单

### 1. xllm_ops 侧输入

必须从 `third_party/xllm_ops` 确认：

- `op_name`、`aclnn_name`、kernel/op type 映射；
- generated header 是否在 `third_party/xllm_ops/build/autogen` 或 package 中可见；
- op package build 和单算子精度是否通过；
- op 的 shape/dtype/layout/optional/inplace 语义；
- 运行时是否依赖 `ASCEND_CUSTOM_OPP_PATH`、`LD_LIBRARY_PATH` 或安装后的 custom OPP。

### 2. Header 声明

在 `xllm_ops/xllm_ops_api.h` 声明 runtime 需要调用的 C++ API。

要求：

- 使用 `torch::Tensor` 或 `at::Tensor` 与现有文件风格一致；
- optional 使用 `std::optional<torch::Tensor>`、`c10::optional<at::Tensor>` 或目标已有模式；
- 返回值准确表达输出或 inplace 语义；
- 不把 xllm_ops 测试 wrapper 的临时参数名原样泄漏到 runtime API。

### 3. Wrapper 实现

新增 `xllm_ops/<op>.cpp`。

推荐结构：

```cpp
#include "core/kernels/npu/aclnn/pytorch_npu_helper.hpp"
#include "core/kernels/npu/xllm_ops/xllm_ops_api.h"

namespace xllm::kernel::npu {

std::tuple<torch::Tensor, torch::Tensor> my_op(const torch::Tensor& x, ...) {
  check_tensor(x, "x", "my_op");
  auto out = torch::empty_like(x);
  EXEC_NPU_CMD(aclnnMyOp, x, ..., out);
  return {out, ...};
}

}  // namespace xllm::kernel::npu
```

若 op 需要手动 `aclTensorList`、workspace 或 stream，参考 `select_unshared_kv.cpp`，
但必须说明为什么不能使用 `EXEC_NPU_CMD`。手动路径尤其要检查资源释放和同步语义。

### 4. CMake

在 `xllm_ops/CMakeLists.txt` 的 `SRCS` 中加入新 wrapper 文件。

检查：

- 文件名只出现一次；
- `INCLUDES` 能找到 generated op headers；
- `DEPS` 包含 `opapi`；
- 没有把 `third_party/xllm_ops/build` 产物提交到源码目录；
- 构建命令使用项目已有入口，不新造脚本。

### 5. Runtime Callsite

上层 callsite 应明确：

- 替换旧实现的范围：prefill/decode、sampler、cache、MoE、SSM 等；
- 支持的 model/dtype/layout/shape；
- unsupported case 的 fallback；
- 是否受 feature flag 或配置项控制；
- 对 graph capture/replay、MTP/speculative、batching、padding 的影响。

不要在 callsite 内加入隐式 CPU 同步。需要读取 shape scalar 时，优先使用 tensor metadata；
必须读取 device 值时要写入风险说明和性能证据。

## 验证规则

| 等级 | 必要证据 |
|---|---|
| static integration | harness 无 required fail |
| build | xLLM 最小相关 target 构建成功 |
| wrapper accuracy | xLLM wrapper 输出与 reference 或 xllm_ops 单算子证据对齐 |
| xLLM smoke | 固定 prompt 或单元测试走到新 callsite |
| e2e accuracy | 目标数据集 subset/full task 无回归 |
| performance | warmup/repeat 的 before/after latency 或 throughput |

若只完成 wrapper 和 CMake，不能宣称 xLLM runtime 已接通。若只跑了单算子精度，不能宣称
end-to-end accuracy 已通过。

## 常见失败模式

- `xllm_ops_api.h` 声明与 `.cpp` 签名不一致；
- CMake 漏加新 `.cpp`，导致链接时找不到 symbol；
- wrapper 分配了错误 dtype/device 的输出；
- optional tensor 在 xllm_ops 测试 wrapper 里可为 `None`，runtime wrapper 却传了空 tensor 或反之；
- `ASCEND_CUSTOM_OPP_PATH` 指到旧 package；
- callsite 没有 fallback，unsupported shape 直接触发 ACL error；
- decode 中 dynamic shape 或 graph replay 参数被 host scalar 固化；
- 为调试留下 `aclrtSynchronizeStream` 或 `.cpu()`。
