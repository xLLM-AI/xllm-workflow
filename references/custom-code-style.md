# xLLM NPU 代码风格指南

> 用于 `xllm-npu-code-review` skill 的补充参考。

## C++ 引擎代码风格

### 命名规范

- **类名**: PascalCase — `ContinuousScheduler`, `ProfileManager`, `MsptiMetrics`
- **成员变量**: snake_case + 尾下划线 — `profile_manager_`, `conv_weight_transposed_`
- **成员函数**: snake_case — `predict_step_time()`, `dump_step_time_profile_to_file()`
- **常量**: kPascalCase — `kMaxBatchSize`, `kDefaultBlockSize`
- **宏**: SCREAMING_SNAKE_CASE — `LLM_MSTX_RANGE()`, `DECLARE_FLAG()`
- **命名空间**: 不使用 namespace（xLLM 引擎代码全局命名空间）

### 头文件

- 使用 `#pragma once` 而非 include guard
- 头文件中的成员变量使用 `mutable` 显式标注可变性
- `std::optional` 用于可选返回值，`std::unique_ptr` 用于所有权转移

### 错误处理

- 禁止静默失败：NPU API 调用必须检查返回值
- NPU 算子调用后使用 `TORCH_CHECK` 或 `AT_ASSERT` 验证
- 使用 `ATB_CHECK_*` 宏检查 ATB 操作结果

### RAII 模式

- 资源管理必须使用 RAII
- `Timer` 用于 scope 计时
- `AutoCounter` 用于 bvar 度量

## Python 脚本风格

### 格式

- 行宽 120 字符
- 使用 `dataclass` 定义配置类
- 类型注解全覆盖（函数签名 + 重要局部变量）

### CLI 脚本

- 使用 `argparse`（不使用 click/typer）
- 必须支持 `--help`
- 输出为 JSONL 或 Markdown（便于自动化）

### 数据处理

- 使用 `pathlib.Path` 而非 `os.path`
- 使用 `logging` 模块（不 `print`）

## NPU 特化代码注意点

### TileLang Kernel

- kernel 函数名：snake_case + `_kernel` 后缀
- 必须标注 `@tilelang.jit` 装饰器
- tiling 参数通过 `T.Kernel` 或函数参数传入
- 避免在 kernel 内部使用 Python 动态特性

### Triton-Ascend Kernel

- 遵循 triton 标准命名：`_kernel` 后缀
- `@triton.jit` 装饰器
- 使用 `tl.program_id`, `tl.arange` 标准 API
- 注意 NPU 上的 `tl.load` / `tl.store` 对齐要求

### ACLNN 调用

- 调用前必须检查 tensor contiguous
- 使用 `LLM_MSTX_RANGE()` 宏标注 profile 区间
- 正确处理 stream 同步
