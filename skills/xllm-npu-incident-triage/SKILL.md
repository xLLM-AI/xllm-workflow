---
name: xllm-npu-incident-triage
description: xLLM 昇腾 NPU 生产事故诊断。Replay-first 流程，收集证据、分类问题、定位根因、验证修复。覆盖 AICore timeout、HCCL 通信失败、NPU OOM、KV Cache 碎片、GE 编译错误、setup.py/cmake/ninja/link 构建失败、submodule 缺失或 build cache 污染等常见问题。当用户报告 xLLM NPU 运行异常、编译失败、构建异常或 rebase 后 build 不稳定时使用。
---

# xLLM NPU 生产事故诊断

## 概述

当 xLLM 在华为昇腾 NPU 上出现以下问题时，使用此 skill 进行诊断：

| 问题类型 | 典型症状 |
|---------|---------|
| AICore timeout | 算子执行超时、NPU hang |
| HCCL 通信失败 | AllReduce 超时、节点间断开 |
| NPU OOM | 显存不足、KV Cache 分配失败 |
| KV Cache 碎片 | 可用显存够但调度失败 |
| GE/AclGraph 错误 | 编译失败、replay 失败 |
| 构建/环境异常 | setup.py/cmake/ninja/link 失败、submodule 未初始化、build cache 污染 |
| 精度异常 | 输出与预期不符、NaN/Inf |
| 性能退化 | 相比历史吞吐下降 |
| PD 分离异常 | Prefill/Decode 延迟不对称 |

## 核心原则

1. **Replay-first**：先复现，再诊断
2. **证据链**：保留从告警到根因的完整证据链
3. **最小化复现**：缩减到能复现的最小场景
4. **修复验证**：每个修复都有回归验证

## 工作流

详见 [references/replay-workflow.md](references/replay-workflow.md)。

### Step 1: 证据保全

在问题发生后立即采集：

```bash
# NPU 状态快照
npu-smi info > artifact/npu_status.log
npu-smi info -t board -i 0 > artifact/npu_board.log

# xLLM 日志
# 收集最近的日志、错误堆栈

# 系统日志
dmesg | tail -200 > artifact/dmesg.log

# 环境变量
env | grep -E "ASCEND|CANN|NPU" > artifact/env.log

# 进程状态
ps aux | grep xllm > artifact/process.log

# NPU 使用率
npu-smi info -t usages > artifact/npu_usages.log
```

保存环境信息到 `artifact/env.json`：
- NPU 型号、数量、驱动版本
- CANN 版本
- xLLM commit hash
- 模型路径和配置
- 触发时间线和操作序列

### Step 2: 问题分类

根据症状分发到对应的子分析流程：

#### 2.1 运行时错误 → Runtime 调试

症状：进程崩溃、段错误、算子执行失败

```bash
# 开启详细日志
export ASCEND_GLOBAL_LOG_LEVEL=1   # INFO 级别
export ASCEND_SLOG_PRINT_TO_STDOUT=1

# 检查 NPU 驱动日志
cat /var/log/dcm/dcm.log | grep -i error
cat /var/log/messages | grep npu
```

常见原因：
- 算子不支持当前 shape/dtype
- AICore 资源耗尽
- 多进程 NPU 内存冲突
- 驱动版本与 CANN 版本不匹配

#### 2.2 精度异常 → 精度调试

症状：输出 NaN/Inf、与 GPU 结果不一致

检查项：
- FP16 溢出（检查 MatMul 前后值范围）
- KV Cache Prefill/Decode 写入对齐
- Softmax 数值稳定性（是否需要 float32 中间结果）
- LayerNorm/RMSNorm 精度
- 权重加载精度（量化误差）

工具：
```bash
# 开启 dump 功能
export ASCEND_OPP_PATH=$ASCEND_HOME/opp/built-in
export ASCEND_ENABLE_DUMP=1
# 配合 xLLM dump 配置
```

#### 2.3 性能退化 → Profiling 分析

症状：吞吐下降、延迟增加

调用 `xllm-npu-profiler` skill：
1. 采集当前 profiling
2. 与历史基线对比
3. 定位退化的具体算子或路径

常见原因：
- 新增算子未融合
- 图模式 fallback（某个 shape 不支持 compilation）
- 小范围 xLLM C++ 修改如果触发 Ninja 重编数百个目标，先按对象级目标验证具体改动，并记录为构建缓存/依赖 churn；不要直接判断为源码修复失败。示例：优先编译 `qwen3_gated_delta_net_base.cpp.o`、`acl_graph_executor_impl.cpp.o`、`mtp_worker_impl.cpp.o`，确认对象通过后再做完整 `python setup.py build` 或目标二进制构建。
- KV Cache 碎片率增加
- 调度参数回归

#### 2.4 通信异常 → HCCL 测试

症状：AllReduce 超时、TP 训练/推理 hang

```bash
# HCCL 单测
cd /path/to/hccl-test
./run_test.sh allreduce

# 检查节点间网络
npu-smi info -t health
hccl_info --device

# 检查拓扑
npu-smi info -t topo
```

常见原因：
- ROCE 网络抖动
- 节点间时间偏移
- HCCL 版本问题（检查 `hccl_version.txt`）

#### 2.5 内存不足 → 内存调试

症状：OOM killed、KV Cache 分配失败

检查项：
- `npu-smi info` 实际显存使用
- xTensor 内存池碎片率
- KV Cache block 数量限制
- Batch size 与显存的关系

```bash
# 查看显存使用详情
npu-smi info -t memory

# xLLM 内部指标
# 检查 xTensor 池的分配日志
```

#### 2.6 PD 分离异常 → 调度调试

症状：Prefill 延迟突然增加、Decode 队列堆积

检查项：
- 请求调度日志（prefill vs decode 分配比例）
- 跨节点网络延迟
- Mooncake 全局 KV Cache 状态
- 节点健康状态

#### 2.7 部署产物缺失 → 先补证据

症状：服务启动失败、healthcheck 超时、首个请求异常、profiling attach 失败、
性能测试后 HBM/PID 残留。

先确认是否有 deploy run artifact：
- 启动命令和完整环境变量。
- `npu-smi.before/after.txt`。
- `visible_devices.txt`。
- `pids.txt`，且 PID 能和 `ps -ef` 对上。
- 每个 node/rank 的日志。
- `/v1/models` healthcheck 输出。
- 最小 smoke 请求和响应。

缺少这些信息时，不要直接开始源码修改；先补最小可复现启动脚本和 artifact，
避免把 HBM 残留、端口残留、HCCL 残留或错误 PID 当成源码 bug。

#### 2.8 构建/环境异常 → Build Environment 调试

症状：`python setup.py build --device npu` 明显比平时慢，或出现与改动无关的编译/链接错误。

先判断是否为环境污染，不要直接归因到本次代码修改：
- OPP 头文件与源码/库不匹配：常见表现是 `aclnnBeamSearchGroup` 签名不一致，或头文件里仍带旧的 `topK` 参数。
- build cache 里的 libtorch 架构错误：常见表现是链接时报 `_deps/libtorch-src/lib/libtorch.so: file in wrong format`。
- Python 开发头缺失：常见表现是找不到 `Python.h`。
- TileLang/小算子缓存被重新触发生成：会让一次普通 build 变成长时间编译，不代表业务代码本身需要这么久。
- vcpkg 或依赖缓存锁在沙箱里不可写：会表现为 lock/cache 相关失败。

快速检查：
```bash
grep -n "aclnnBeamSearchGroup" /usr/local/Ascend/ascend-toolkit/latest/opp/vendors/xllm/op_api/include/aclnn_beam_search_group.h
file build/cmake.linux-aarch64-cpython-311/_deps/libtorch-src/lib/libtorch.so
file /usr/local/lib64/python3.11/site-packages/torch/lib/libtorch.so
```

处理原则：
- 标准路径仍应是 `python setup.py build --device npu`；如果需要额外 `CMAKE_ARGS`、临时 OPP 目录或 libtorch symlink，要在验证报告里显式标注为环境规避。
- 不建议直接覆盖系统 `/usr/local/Ascend/.../opp/vendors/xllm`，优先使用匹配当前源码的临时 OPP vendor 目录，或在干净环境重新安装 xllm ops。
- 若 build 因 cache 命中错误架构 libtorch 失败，只清理/修正 build artifact，避免改动源码来绕过环境问题。
- 构建异常解决后，仍需做 `sampler_test`、短请求 smoke、目标 workload perf 与小样本精度验证。

### Step 3: 复现工作流

详见 [references/replay-workflow.md](references/replay-workflow.md)。

目标：
1. 确定能稳定复现的最小输入
2. 确定问题发生的条件（特定 batch size、序列长度、并发数）
3. 记录复现命令，确保团队可独立验证

### Step 4: 根因分析 + 修复验证

```markdown
## 事故报告

### 时间线
（从告警到修复的完整时间线）

### 症状
（用户看到的异常现象）

### 根因
（技术细节：哪个代码路径、哪个配置、哪个外部因素）

### 修复
（代码变更/配置变更/环境修复）

### 验证
（回归测试结果）

### 预防措施
（如何避免同类问题再次发生）
```

## NPU 错误目录

详细错误码和处理建议见 [references/npu-error-catalog.md](references/npu-error-catalog.md)。

关键错误码摘要：

| 错误码 | 含义 | 常见原因 |
|--------|------|---------|
| E39999 | AICore 算子超时 | 算子实现 bug 或硬件问题 |
| E50000 | 通信超时 | ROCE 网络或拓扑问题 |
| E82000 | 显存不足 | 显存碎片或配置不当 |
| E40010 | 图编译失败 | 不支持的算子或 shape |
| E30001 | 输入参数错误 | dtype/shape 不匹配 |

## 参考资料

按需加载：
- [references/npu-error-catalog.md](references/npu-error-catalog.md) — 完整 NPU 错误码目录
- [references/replay-workflow.md](references/replay-workflow.md) — 复现工作流模板
- [references/ascend-profiling-formats.md](../xllm-npu-profiler/references/ascend-profiling-formats.md) — Profiling 数据格式

## 实测事故案例

历史事故示例见
[`references/incident-case-studies.md`](references/incident-case-studies.md)。常规排障
优先按上面的 evidence-first 流程执行。
