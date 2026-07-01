# xLLM Profiler 源码地图

> 快速定位 xLLM profiler 相关代码，用于 NPU trace 采集和分析。

## 一、C++ 核心 Profiler 模块

### 推理时延 Profile（调度层）

| 文件 | 说明 |
|------|------|
| `core/scheduler/profile/profile_manager.h/.cpp` | **`ProfileManager`** — 核心 profiler，prefill/decode 时延采样、`TimePredictor` 训练、dump 数据到文件 |
| `core/scheduler/profile/time_predictor.h/.cpp` | **`TimePredictor`** — Eigen 多项式回归时延预测器，`fit_for_prefill()` / `fit_for_decode()` / `predict_time()` |
| `core/scheduler/profile/CMakeLists.txt` | 编译为 `profile` 静态库 |

### 输出文件

`ProfileManager::dump_step_time_profile_to_file()` 写入当前工作目录：
- `{YYYYMMDD_HHMMSS}_profile_prefill_step_time.txt` — CSV: `token_length,prefix_length,latency_ms`
- `{YYYYMMDD_HHMMSS}_profile_decode_step_time.txt` — CSV: `token_length,batch_size,latency_ms`

## 二、NPU 硬件级 Tracing（MSPTI）

| 文件 | 说明 |
|------|------|
| `core/common/mspti_helper.h` | **`MsptiMetrics`** 类 + `LLM_MSTX_RANGE()` 宏 — 华为 NPU 硬件追踪入口 |
| `core/common/mspti_helper.cpp` | 实现 — 注册/释放 MSPTI 订阅器，解析 Marker/Memory/HCCL/Kernel 事件 |

### MSPTI 事件类型

- **Marker**: 算子级标注
- **Memory**: 内存分配/释放事件
- **HCCL**: 集合通信事件（AllReduce, AllGather 等）
- **Kernel**: AI Core 算子执行事件

### Trace 写入路径

由 `MsptiMetrics::user_buffer_complete()` 回调输出到自定义日志文件（由 MSPTI 订阅器配置决定路径）。

## 三、NPU Timeline 可视化工具

| 文件 | 说明 |
|------|------|
| `tools/npu_timeline.py` | 解析 MSPTI 日志 → Chrome Trace Format JSON（`chrome://tracing` 查看） |
| `tools/README.md` | 使用指南：`MsptiMetrics::register_subscriber()` → `LLM_MSTX_RANGE()` → `release_subscriber()` |

## 四、Profile 配置入口

### GFlags（C++ 命令行）

| Flag | 说明 |
|------|------|
| `enable_profile_step_time` | 启用 step time profile |
| `enable_profile_token_budget` | 启用 token budget profile |
| `profile_max_prompt_length` | profile 最大 prompt 长度 |
| `enable_profile_kv_blocks` | 启用 KV block 拷贝时延 profile |
| `disable_ttft_profiling` | 禁用启动时 TTFT profiling |
| `max_global_ttft_ms` / `max_global_tpot_ms` | TTFT/TPOT SLA 上限 |

定义位置：`core/common/global_flags.cpp` / `global_flags.h`

### 选项传递链

```
xllm.cpp (main, L308-312)
  → Options (core/common/options.h)
    → ContinuousScheduler (core/scheduler/continuous_scheduler.h/.cpp)
      → ProfileManager (core/scheduler/profile/profile_manager.h/.cpp)
```

### Python 入口

- `pybind/llm.py` (L129, L194): `LLM` 类接收 `disable_ttft_profiling`
- `pybind/args.py` (L41): argparse 定义 `--disable_ttft_profiling`

## 五、Scheduler 中的 Profile 使用方

| Scheduler | Profile 用途 |
|-----------|-------------|
| `ContinuousScheduler` | 持有 `ProfileManager`，管理 profile options |
| `ChunkedPrefillScheduler` | `predict_step_time()` + `get_token_budget()` 决定 chunk 大小 |
| `MixScheduler` | `predict_step_time()` / `predict_copy_blocks_time()` / `get_max_copy_block_num()` 做 latency-aware 调度 |
| `PrefillOnlyScheduler` | `predict_step_time()` 估计 prefill 时延 |
| `DisaggPDScheduler` | `profile_ttft()` / `profile_tpot()` 实测 TTFT/TPOT 查找表 |

## 六、辅助性能度量工具

| 文件 | 说明 |
|------|------|
| `core/common/metrics.h` | `GAUGE`, `COUNTER`, `HISTOGRAM`, `AUTO_COUNTER` 宏（基于 bvar） |
| `core/util/timer.h/.cpp` | `Timer` 高精度计时器 |

## 七、编译器层 msprof 引用

- `compiler/tilelang/targets/ascend/toolchain.py` (L97): 将 `{npu_home_path}/include/experiment/msprof` 加入 include 路径，tile 代码可使用华为 msprof 头文件
