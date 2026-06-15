# Triton 算子迁移到 torch_npu_ops Runbook

本文基于 `fused_qkvzba_split_reshape_cat` 算子迁移实践整理，用于把
vLLM-Ascend 中的 Triton 自定义算子迁移到 `torch_npu_ops` 或 xLLM 的
Triton-Ascend AOT 形态。

## 迁移目标

迁移完成后应具备：

- Python Triton kernel + pytest 精度验证；
- AOT 编译生成单一 `.npubin`；
- C++ torch lib 接口封装；
- C++ GTest 测试用例；
- CMake 接入和可复查的验证日志。

## 目标文件结构

```text
torch_npu_ops/
├── triton_npu/
│   ├── triton_src/
│   │   └── test_<op_name>.py
│   ├── torch_api/
│   │   ├── operations.h
│   │   ├── operation_factory.h
│   │   ├── triton_ops_api.h
│   │   └── npu_triton_<op_name>.cpp
│   ├── test/
│   │   └── triton_<op_name>_test.cpp
│   └── binary/
│       └── <kernel_name>.npubin
├── CMakeLists.txt
└── triton_npu/test/CMakeLists.txt
```

## Python Triton Kernel

关键原则：

1. 所有可能在模型运行时变化的参数，例如 `batch_size`、`num_heads`，必须使用
   `do_not_specialize`；
2. `tl.arange(0, N)` 中的 `N` 必须是 `tl.constexpr`；
3. 当循环次数是运行时变量时，使用 `tl.range`，不要使用 `tl.static_range`；
4. wrapper 中预计算 constexpr 值后传给 kernel；
5. pytest 用例必须覆盖多个典型参数组合并对比 reference。

示例：

```python
@triton.jit(do_not_specialize=["batch_size", "num_heads"])
def kernel_name(
    out_ptr,
    in_ptr,
    batch_size,
    num_heads,
    CONST_DIM: tl.constexpr,
):
    for i in tl.range(batch_size):
        idx = tl.arange(0, CONST_DIM)
        ...


def triton_op_wrapper(input_tensor, param1, param2):
    const_dim = param1 * param2
    grid = (grid_size,)
    kernel_name[grid](
        output,
        input_tensor,
        runtime_batch,
        runtime_heads,
        const_dim,
    )
    return output
```

## C++ Op 定义

`operations.h`：

```cpp
class FusedQkvzbaSplitReshapeOp final : public OperationBase {
 public:
  FusedQkvzbaSplitReshapeOp()
      : OperationBase("fused_qkvzba_split_reshape_cat_kernel") {}
};
```

`operation_factory.h`：

```cpp
FusedQkvzbaSplitReshapeOp& fused_qkvzba_split_reshape() {
  return get_or_create<FusedQkvzbaSplitReshapeOp>(
      "fused_qkvzba_split_reshape_cat_kernel");
}
```

`triton_ops_api.h`：

```cpp
std::tuple<torch::Tensor, torch::Tensor, torch::Tensor, torch::Tensor>
npu_fused_qkvzba_split_reshape_cat(
    torch::Tensor& mixed_qkvz,
    torch::Tensor& mixed_ba,
    int32_t num_heads_qk,
    int32_t num_heads_v,
    int32_t head_qk,
    int32_t head_v);
```

## C++ Wrapper

`torch_api/npu_triton_<op>.cpp` 中要保证 `ArgsBuilder` 参数顺序与 Triton kernel
签名完全一致。

Vector Core 查询示例：

```cpp
static int32_t get_vectorcore_num() {
  int32_t device_id = 0;
  if (aclrtGetDevice(&device_id) != ACL_SUCCESS) {
    return 20;
  }
  int64_t vec_core_num = 0;
  const aclError ret = aclrtGetDeviceInfo(
      static_cast<uint32_t>(device_id),
      ACL_DEV_ATTR_VECTOR_CORE_NUM,
      &vec_core_num);
  if (ret == ACL_SUCCESS && vec_core_num > 0) {
    return static_cast<int32_t>(vec_core_num);
  }
  return 20;
}
```

Wrapper 结构：

```cpp
std::tuple<...> npu_fused_qkvzba_split_reshape_cat(...) {
  const int32_t num_vectorcore = get_vectorcore_num();
  const int32_t grid_size = std::max(1, std::min(num_vectorcore, total_rows));

  auto& op = OperationFactory::instance().fused_qkvzba_split_reshape();
  auto ret = op.execute(stream, gridX, gridY, gridZ, [&](ArgsBuilder& ab) {
    ab.constructArgs(
        out_ptr,
        in_ptr,
        runtime_param1,
        runtime_param2,
        constexpr_param1);
  });
}
```

## C++ GTest

```cpp
TEST_P(TritonOpTest, OpTest) {
  auto input = torch::randn({batch, dim}, options);
  auto ref = cpu_reference(input);
  auto out = npu_op(input.npu());
  auto diff = torch::abs(ref - out.cpu());
  EXPECT_LT(torch::max(diff).item<float>(), 1e-2);
}
```

## CMake

根 `CMakeLists.txt`：

```cmake
set(TRITON_NPU_API_SRCS
  ...
  triton_npu/torch_api/npu_triton_<op_name>.cpp
)
```

`triton_npu/test/CMakeLists.txt`：

```cmake
cc_test(
  NAME
    <op_name>_test
  SRCS
    triton_<op_name>_test.cpp
  DEPS
    GTest::gtest
    GTest::gtest_main
    triton_adapter
    torch
    torch_npu
)
```

## 验证流程

```bash
cd torch_npu_ops/triton_npu
python3 setup.py

# 预期：
# - pytest: X passed
# - Found 1 unique kernel(s)
# - Copied <kernel_name>.npubin -> binary/

cd build
cmake ..
make -j triton_adapter
make -j <op_name>_test
./triton_npu/test/<op_name>_test
```

## 常见问题

### 多个 binary 生成

现象：`ERROR: Multiple binaries found for kernel 'xxx'`。

根因：参数被编译器常量折叠，不同测试用例产生不同 binary。

处理：

```python
@triton.jit(do_not_specialize=["num_heads"])
def kernel(..., num_heads):
    ...
```

不要把运行时变化参数同时标成 `tl.constexpr`。

### `tl.arange` 需要编译时常量

```python
@triton.jit
def kernel(..., TILE_SIZE: tl.constexpr):
    idx = tl.arange(0, TILE_SIZE)
```

如果 tile size 来自运行时输入，在 Python wrapper 里预计算后作为 constexpr 传入。

### `do_not_specialize` 与 `tl.constexpr` 互斥

运行时变量使用 `do_not_specialize`，编译期 tile/layout 参数使用 `tl.constexpr`。
不要让同一参数同时承担两种角色。

### AI Core vs Vector Core

Triton 通常运行在 Vector Core 上，grid size 应查询 `ACL_DEV_ATTR_VECTOR_CORE_NUM`。
不要用 `ACL_DEV_ATTR_AICORE_CORE_NUM` 估算 vector 算子并行度。

## 快速检查清单

- [ ] Triton kernel 使用 `do_not_specialize` 标记运行时变量；
- [ ] `tl.arange` 只使用 `tl.constexpr` 参数；
- [ ] 遍历运行时变量时使用 `tl.range`；
- [ ] pytest 覆盖不同参数组合；
- [ ] AOT 编译产生单一 binary；
- [ ] C++ 接口参数顺序与 Triton kernel 签名一致；
- [ ] C++ 使用 `ACL_DEV_ATTR_VECTOR_CORE_NUM` 获取 AIV 核数；
- [ ] GTest 精度验证通过；
- [ ] 构建、pytest、GTest 日志已保存到 run 目录或报告中。
