# Replay 工作流模板

## 概述

Replay-first 是 xLLM NPU 事故诊断的核心原则：先稳定复现问题，再进行根因分析。

## 工作流模板

### 1. 信息收集

```markdown
## 事件信息

- **报告时间**: YYYY-MM-DD HH:MM
- **报告人**: [姓名]
- **影响范围**: [哪些服务/用户受到影响]
- **发生频率**: [每次/偶发/特定条件]
- **最近变更**: [最近 24 小时内的代码/配置/环境变更]
```

### 2. 环境快照

```bash
# 创建 artifact 目录
mkdir -p artifacts/$(date +%Y%m%d_%H%M%S)

# NPU 状态
npu-smi info > artifacts/npu_status.log
npu-smi info -t board > artifacts/npu_board.log
npu-smi info -t usages > artifacts/npu_usages.log
npu-smi info -t topo > artifacts/npu_topo.log

# 系统日志
dmesg | tail -500 > artifacts/dmesg.log
journalctl -u xllm --since "1 hour ago" > artifacts/xllm_journal.log

# 进程状态
ps aux | grep xllm > artifacts/processes.log
lsof -p <xllm_pid> > artifacts/lsof.log

# xLLM 日志
cp /var/log/xllm/*.log artifacts/

# 环境变量
env | grep -E "ASCEND|CANN|NPU|XLLM" > artifacts/env.log
```

### 3. 最小化复现

目标：确定能稳定复现的最小输入和条件。

```markdown
## 复现条件

- **最小 batch size**: [N]
- **最小序列长度**: [input=M, output=K]
- **触发频率**: [X/Y 次]
- **必要条件**: [特定配置/特定模型/特定 NPU 卡]
```

复现命令：
```bash
# 最小复现命令
xllm serve /path/to/model \
  --tensor-parallel-size 4 \
  --max-num-seqs <最小触发值> \
  --graph-mode npugraph_ex
```

### 4. 对比测试

对比正常和异常状态：

| 维度 | 正常 | 异常 | 差异 |
|------|------|------|------|
| NPU 显存使用 | X GB | Y GB | Z GB |
| AICore 利用率 | 85% | 60% | -25% |
| 请求延迟 p50 | 150ms | 500ms | +350ms |
| 日志错误 | 无 | E39999 | AICore timeout |

### 5. 根因分析

```markdown
## 根因分析

### 直接原因
（导致问题的具体代码路径/配置/外部因素）

### 根本原因
（为什么这个问题会出现）

###  Contributing factors
（加剧问题的因素）
```

### 6. 修复验证

```markdown
## 修复记录

### 修复方案
（代码变更/配置变更描述）

### 验证结果
- 复现命令是否仍然触发问题: [Yes/No]
- 回归测试结果: [Pass/Fail]
- 性能影响: [N/A / +X% / -Y%]

### 预防措施
（如何避免同类问题）
```

## 常见复现模式

### 模式 A: 显存相关

1. 固定显存使用量
2. 逐步增加并发
3. 找到触发 OOM 的阈值

### 模式 B: 精度相关

1. 使用固定随机种子
2. 对比 GPU 和 NPU 输出
3. 找到 diverge 的层

### 模式 C: 性能退化

1. 回滚到已知正常的 commit
2. bisect 找到引入退化的 commit
3. 对比退化的 profiling
