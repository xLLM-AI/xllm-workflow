# 昇腾 Profiling 数据格式说明

## 概述

华为昇腾 NPU Profiling 工具（msprof / ascend profiling）输出以下标准文件：

```
profiling_result/
├── step_trace_time.csv     # Step 级别时间追踪
├── op_statistic.csv        # 算子调用统计
├── kernel_details.csv      # AICore kernel 详细时间
├── analysis.db             # SQLite 详细分析数据
├── host_info.csv           # Host 侧时间信息
└── op_trace/               # 详细算子 trace 目录
    ├── op_trace_0.csv
    ├── op_trace_1.csv
    └── ...
```

## 关键文件格式

### step_trace_time.csv

Step 级别时间追踪，每个迭代步的时间分解。

```csv
Step ID,Total Time(us),AICore Time(us),AICPU Time(us),Host Time(us),Idle Time(us),Dispatch Latency(us)
0,15234,12100,500,1200,1434,320
1,14890,12050,480,1100,1260,310
```

字段说明：
- `Step ID`: 迭代步编号
- `Total Time(us)`: 总耗时（微秒）
- `AICore Time(us)`: AICore 计算时间
- `AICPU Time(us)`: AICPU（CPU 算子）时间
- `Host Time(us)`: Host 侧处理时间
- `Idle Time(us)`: NPU 空闲时间
- `Dispatch Latency(us)`: 算子下发达延迟

**瓶颈判定**：
- `Idle Time / Total Time > 20%` → Hostbound
- `AICore Time / Total Time > 85%` → Computing
- `Communication Time / Total Time > 10%` → Communication（需从 kernel_details 提取）

### op_statistic.csv

算子调用统计。

```csv
Op Name,Op Type,Count,Total Duration(us),Avg Duration(us),Max Duration(us),Min Duration(us)
MatMul_0,MatMul,1024,8500000,8300,12000,6500
Add_0,Add,2048,500000,244,800,120
Softmax_0,Softmax,512,2500000,4883,8500,3200
```

字段说明：
- `Op Name`: 算子实例名
- `Op Type`: 算子类型
- `Count`: 调用次数
- `Total Duration(us)`: 总耗时
- `Avg/Max/Min Duration(us)`: 平均/最大/最小耗时

### kernel_details.csv

AICore kernel 详细时间。

```csv
Kernel Name,Op Name,Count,Total Duration(us),Avg Duration(us),Block Dim,AICore Utilization(%)
MatMul_0_kernel,MatMul_0,1024,8200000,8000,64,92.3
Add_0_kernel,Add_0,2048,450000,220,16,78.5
```

字段说明：
- `Kernel Name`: AICore kernel 名称
- `Op Name`: 对应的算子名
- `Count`: 调用次数
- `Total Duration(us)`: 总耗时
- `AICore Utilization(%)`: AICore 利用率

### analysis.db (SQLite)

包含更详细的分析数据：

**常用查询**：

```sql
-- 查看 Top 算子
SELECT * FROM operator_statistics ORDER BY total_duration DESC LIMIT 20;

-- 查看 kernel 占比
SELECT kernel_name, SUM(duration) as total, COUNT(*) as count
FROM kernel_events GROUP BY kernel_name ORDER BY total DESC LIMIT 20;

-- 查看通信算子
SELECT * FROM operator_statistics WHERE op_type IN ('AllReduce', 'AllGather', 'ReduceScatter') ORDER BY total_duration DESC;

-- 查看各阶段 AICore 利用率
SELECT step_id, aicore_time, total_time,
       ROUND(aicore_time * 100.0 / total_time, 2) as utilization
FROM step_trace ORDER BY step_id;
```

## 采集方式

### xLLM dynamic attach

当前 xLLM 源码未发现 `XLLM_PROFILING` 环境变量读取点。xLLM NPU profiling
优先使用启动侧 `PROFILING_MODE=dynamic`，再通过 `msprof --dynamic=on --pid`
attach 到 xLLM 父进程并用 `start/stop` 控制采集窗口。

```bash
export PROFILING_MODE=dynamic
xllm serve ...
msprof --dynamic=on --pid <xllm_parent_pid> --output /path/to/profiling_output
```

### 昇腾 msprof

```bash
msprof --application-profiling=on \
  --ai-core \
  --output-dir /path/to/profiling_output \
  -- python your_script.py
```

### 环境变量方式

```bash
export ASCEND_GLOBAL_LOG_LEVEL=1
export ASCEND_HOST_SCHED_V2=1  # Host 调度详细日志
export ENABLE_HOST_TILING_DUMP=1  # Tiling 信息 dump
```

## 文件路径约定

xLLM 的 profiling 输出默认写入：
- xLLM 内置：`/tmp/xllm_profiling/<pid>/`
- msprof：用户指定的 `--output-dir`

vLLM-Ascend 需通过 `--profiler-config` 配置输出路径。
