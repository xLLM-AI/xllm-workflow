---
name: xllm-npu-accuracy-debug
description: xLLM 昇腾 NPU 精度异常定位。用于输出不是人话、答案错误、CEval/GSM8K 等数据集掉分、GPU/NPU 结果不一致、某个 PR 或 commit 疑似引入精度回归时，按日志代码审查、最小复现、验证强度阶梯、commit 二分和根因归档流程定位问题。
---

# xLLM NPU 精度异常定位

## 概述

当 xLLM 在昇腾 NPU 上出现以下现象时使用本 skill：

| 症状 | 例子 |
|------|------|
| 输出不是人话 | 重复、乱码、格式崩坏、答非所问 |
| 简单 prompt 错误 | 单题数学、常识、选择题明显错误 |
| 局部数据集掉分 | CEval 某几个 task、GSM8K 小样本下降 |
| 全量评测回归 | CEval / GSM8K / MMLU 等整体准确率下降 |
| 版本间结果差异 | 某个 PR 或 commit 后开始出错 |
| 后端差异 | GPU 正常、NPU 异常，或 eager 正常、graph 异常 |

目标不是一开始就跑最贵的全量评测，而是建立一条从最轻量 sanity 到全量 benchmark 的证据链，逐步缩小问题范围。

## 核心原则

1. **先复现，再解释**：先拿到可重复输入、输出、命令和 commit。
2. **验证成本递增**：从单 prompt 到小样本，再到全量数据集。
3. **A/B 同条件**：只改变一个变量，例如 commit、开关、后端、kernel 或 batch 参数。
4. **代码和日志并行看**：不要只看指标；权重加载、KV Cache、采样、graph capture 都要查。
5. **坏例优先**：找到一条稳定坏例，比先跑全量更有效。
6. **证据归档**：保存 prompt、target、prediction、日志、commit、启动参数和输出目录。

正式精度产物必须遵循
[`../../references/accuracy-artifact-schema.md`](../../references/accuracy-artifact-schema.md)；
run 元信息遵循
[`../../references/run-manifest-template.md`](../../references/run-manifest-template.md)。
如果只是单 prompt 或 5-10 条 smoke，报告中必须标为 L1/L2，不能扩大成完整
精度结论。

## 验证强度阶梯

| 等级 | 验证方式 | 目标 | 成本 | 可用于 |
|------|----------|------|------|--------|
| L0 | 服务启动 + 日志无异常 | 排除 OOM/HCCL/graph 初始化失败 | 很低 | 环境确认 |
| L1 | 单个 prompt 是否是人话 | 判断模型是否明显坏掉 | 很低 | 快速 sanity |
| L2 | 5-10 条确定性 prompt | 判断是否有明显精度崩坏 | 低 | 修复后 smoke |
| L3 | 数据集子集前 N 条 | 发现可复现坏例 | 中 | PR A/B 对照 |
| L4 | 单个 task 全量 | 判断局部 task 是否回归 | 中高 | 精度回归定位 |
| L5 | 全量评测集 | 形成最终指标结论 | 高 | 合入前验收 |

建议先做到 L3，再决定是否跑 L4/L5。

## 工作流

### Step 1: 记录问题现场

先固定以下信息：

```bash
git -C /path/to/xllm rev-parse HEAD
git -C /path/to/xllm status --short
npu-smi info
env | grep -E "ASCEND|CANN|NPU|HCCL|ATB|PYTORCH_NPU"
```

记录：

- 模型路径和模型类型
- 启动参数：TP、DP、MTP、chunk prefill、graph、schedule overlap、backend
- 物理卡和 `ASCEND_RT_VISIBLE_DEVICES`
- 请求参数：temperature、top_p、top_k、max_tokens、thinking mode
- 数据集、subset、limit、随机种子
- 错误样本：prompt、target、prediction、extracted answer

### Step 2: 最小复现

按验证强度阶梯推进：

1. L1：单个 prompt 看输出是否是人话。
2. L2：固定 5-10 条短 prompt，覆盖数学、选择题、格式遵循。
3. L3：选最可能暴露问题的 task 前 N 条，例如 CEval `operating_system`、`computer_architecture`，或 GSM8K 前 10 条。
4. L4/L5：只有当 L3 显示差异或需要最终验收时再跑。

CEval 两个子集和二分脚本模板见
[`references/accuracy-debug-runbook.md`](references/accuracy-debug-runbook.md)。

### Step 3: 日志和代码逻辑分析

优先查以下路径：

#### 3.1 权重加载

检查点：

- safetensors 是否并发加载多个分片。
- `load_state_dict()` 是否有就地变换：`add_()`、`copy_()`、`set_()`、`transpose().contiguous()`。
- 普通 bool 是否保护跨线程临界区。
- 权重是否可能重复变换或漏变换。
- 量化/反量化参数是否和 checkpoint 对齐。

典型风险：

- q/k norm 权重重复 `add_(1.0)`。
- qkv rows 重排重复执行。
- tilelang/自定义 kernel 期望的 layout 与权重实际 layout 不一致。

#### 3.2 Prefill / Decode 一致性

检查点：

- Prefill 和 Decode 是否走不同 kernel。
- chunk prefill 是否改变 position ids、slot mapping、block table。
- KV Cache 写入是否对齐，尤其是 page/block 边界。
- prefix cache 命中后是否复用错 cache。

#### 3.3 Graph / Eager 差异

检查点：

- `--enable_graph=false` 是否恢复精度。
- graph capture bucket 是否覆盖当前 shape。
- graph replay 是否使用了 stale tensor 或 stale pointer。
- 动态 shape 参数是否参与 capture。

#### 3.4 Sampling / Spec Decode

检查点：

- greedy 与 sampling 是否都异常。
- MTP / draft model 关闭后是否恢复。
- rejection sampler 是否正确处理 accepted/rejected token。
- logits processor、temperature、top_k/top_p 是否和基线一致。

#### 3.5 NPU 自定义算子

检查点：

- dtype：FP16/BF16/FP32 中间结果是否一致。
- layout：ND/NZ、contiguous、transpose、view 是否符合 kernel 约束。
- mask、causal、position encoding 是否一致。
- graph 模式和 eager 模式是否用同一实现。

### Step 4: A/B 对照

每次只改变一个变量：

| 变量 | 对照方式 |
|------|----------|
| commit | good commit vs bad commit |
| graph | `--enable_graph=false/true` |
| chunk prefill | `--enable_chunked_prefill=false/true` |
| MTP | `--num_speculative_tokens=0/N` |
| kernel backend | torch/eager vs custom kernel |
| TP | TP=1/2/4 |
| sampling | greedy vs official sampling config |

结果记录格式：

```markdown
| 版本/配置 | task | Num | Score | 异常样本 |
|-----------|------|-----|-------|----------|
| baseline  | ceval_operating_system | 10 | 10/10 | - |
| suspect   | ceval_operating_system | 10 | 9/10 | index 8: B -> D |
```

### Step 5: Commit 二分查找

当不知道是哪次提交引入问题时，用二分定位。

前提：

- 已有一个稳定坏例或小数据集命令。
- 能定义 `good` 和 `bad` commit。
- 验证脚本返回码能表达 pass/fail。

手工和自动二分模板见
[`references/accuracy-debug-runbook.md`](references/accuracy-debug-runbook.md)。

二分时要避免：

- 把环境 OOM、HCCL 失败误判为精度 bad。
- 在每个 commit 使用不同 sampling 参数。
- 复用上一轮服务进程或 KV cache。
- 对非确定性 sampling 只跑一次就下结论。必要时跑 2-3 次。

### Step 6: 根因归类

常见精度根因分类：

| 类别 | 典型根因 |
|------|----------|
| 权重加载 | 重复变换、漏加载、并发竞态、量化参数不匹配 |
| Layout | transpose/reshape/view 语义错误，ND/NZ 混用 |
| KV Cache | block table、slot mapping、prefix cache、chunk prefill 边界 |
| Position | rope/mrope、position ids、sequence length 计算错误 |
| Kernel | mask、dtype、边界条件、workspace、特殊 shape |
| Graph | capture stale state、bucket 错配、动态 shape 未参数化 |
| Sampling | logits processor、top_k/top_p、repetition penalty、spec verify |
| 分布式 | TP shard、allreduce/allgather、rank 间状态不一致 |

### Step 7: 修复验证

修复后至少做：

1. L2 smoke：5-10 条简单 prompt。
2. L3：复现坏例所在子集前 N 条。
3. 精确坏例回归：修复前错、修复后对。
4. 如果改动影响公共路径，补 L4 或 L5。
5. 单测或构建验证：例如 `sampler_test`、相关 kernel test、完整 `xllm` target。

报告模板：

```markdown
## 精度异常定位报告

### 现象
- 模型/commit/配置：
- 异常样本：
- 期望输出：
- 实际输出：

### 复现
- 启动命令：
- 评测命令：
- 输出目录：

### A/B 结果
| 版本 | task | score | 坏例 |

### 根因
- 代码路径：
- 触发条件：
- 为什么会影响精度：

### 修复
- 改动点：
- 风险：

### 验证
- smoke：
- 子集：
- 全量：
```

## 真实案例：PR #1400 Qwen3-Next 权重变换竞态

这个案例说明：10 条普通 prompt 没问题，不代表没有精度回归；CEval 局部
task 的前 N 条可以更快暴露权重加载竞态。

该类问题应优先保留稳定坏例、A/B 结果、根因和修复验证记录。
