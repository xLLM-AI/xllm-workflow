# xLLM AI Coding Workflow

语言：[English](README.md) | [简体中文](README_zh.md)

面向昇腾 NPU 大模型推理优化的 agent-ready 工作流、Prompt、证据规范和参考知识库。

当前首个支持的落地目标是
[xLLM](https://github.com/jd-opensource/xllm)。同时，本仓库也把
[vLLM-Ascend](https://github.com/vllm-project/vllm-ascend) 和 SGLang NPU
作为公平对比基线、可复用参考和后续适配目标。

本仓库不是 xLLM 运行时本身，也不是 benchmark 结果归档。它提供一套可复用的
AI Coding 工作流，帮助工程师和 coding agent 做公平评测、采集 profiling 证据、
定位精度回归、review NPU 相关改动，并沉淀优化经验。

## 适用场景

当你需要处理以下任务时，可以使用本仓库：

- 优化 NPU 推理的 TTFT、TPOT、TPS、内存或并发能力；
- 公平比较 xLLM 和其他 OpenAI-compatible NPU serving 框架；
- 定位乱码输出、数据集掉分、GPU/NPU 不一致、crash、OOM、图模式失败或 HCCL 问题；
- 为 xLLM NPU PR 准备或 review 可复现的验证证据；
- 在 profiling 证明有必要后，迁移或原型验证 NPU 算子；
- 把一次性的优化经验转化为可复用的 agent skill 和 reference。

本仓库不提供模型权重、私有 benchmark 数据集、生产日志，也不承诺某个特定环境下的
性能数字。所有性能和精度结论都需要在使用者自己的硬件和软件环境中复现。

## 快速开始

### 1. 安装 Skills

推荐使用 symlink，这样后续 `git pull` 后 skills 会自动更新：

```bash
export AGENT_SKILL_DIR="${CODEX_HOME:-$HOME/.codex}/skills"   # Codex 示例
# export AGENT_SKILL_DIR="$HOME/.claude/skills"               # Claude Code 示例

mkdir -p "$AGENT_SKILL_DIR"
for skill_dir in skills/xllm-npu-*; do
  ln -sfn "$(pwd)/$skill_dir" "$AGENT_SKILL_DIR/$(basename "$skill_dir")"
done
ln -sfn "$(pwd)/kernel-pilot" "$AGENT_SKILL_DIR/xllm-npu-kernel-pilot"
ln -sfn "$(pwd)/model-pr-optimization-history" "$AGENT_SKILL_DIR/model-pr-optimization-history"
```

如果目标 agent 不支持 symlink，也可以直接复制需要的 skill 目录。

### 2. 选择任务 Prompt

从 [`prompts/`](prompts/) 复制一个模板，并填入模型、硬件、框架、workload 和目标指标。

| Prompt | 场景 |
|---|---|
| [`xllm-npu-sota-loop-prompts.md`](prompts/xllm-npu-sota-loop-prompts.md) | 端到端优化、TPOT 目标、decode gap、MTP 验证 |
| [`xllm-npu-eval-profiler-prompts.md`](prompts/xllm-npu-eval-profiler-prompts.md) | 服务启动、evalscope、profiling、容量和 OOM 分析 |
| [`xllm-npu-pr-fix-prompts.md`](prompts/xllm-npu-pr-fix-prompts.md) | PR 回归、review 回复、rebase、编译和 UT 门禁 |
| [`xllm-npu-op-migration-prompts.md`](prompts/xllm-npu-op-migration-prompts.md) | 算子迁移、torch_npu、Triton-Ascend、AscendC、ATB |

### 3. 按证据闭环推进

正式优化任务应留下足够证据，方便其他贡献者复现结论：

```text
target -> baseline -> profiling -> patch -> accuracy -> performance -> record
```

Profiling 用于解释瓶颈，不能替代非 profiling 的 before/after 性能对比。

## 仓库内容

| 模块 | 内容 |
|---|---|
| [`skills/`](skills/) | 面向评测、profiling、benchmark、精度定位、事故定位、PR review 和算子迁移的过程化 agent skills |
| [`prompts/`](prompts/) | 可直接复制的中文任务 Prompt 模板 |
| [`references/`](references/) | run manifest、性能、精度、profiling、NPU 规格和代码风格等共享规范 |
| [`docs/`](docs/) | 通用 NPU AI Coding 工作流文档 |
| [`model-pr-optimization-history/`](model-pr-optimization-history/) | 可查询的模型和 PR 历史知识，用于优化决策 |
| [`humanize/`](humanize/) | run-level ledger 约定，用于记录决策、review 反馈和经验 |
| [`kernel-pilot/`](kernel-pilot/) | profiling 证明需要底层优化后使用的 kernel 实验 helper |
| [`patches/`](patches/) | 最小 patch 或迁移说明，不保存完整文件快照 |

## 架构

![xLLM AI Coding Workflow](docs/assets/xllm-ai-coding-workflow-zh.png)

仓库围绕执行闭环和可复用证据存储组织：

| 层级 | 入口 | 责任 |
|---|---|---|
| Orchestrator | `xllm-npu-sota-loop` | 协调 Research、Learn、Code、Review、Validate、Record |
| Execution & Collection | `xllm-npu-eval-runner`、`xllm-npu-profiler`、`xllm-npu-incident-triage` | 启动服务、运行评测、采集 profiling、复现事故、收集原始 artifacts |
| Analysis & Decision | benchmark / pipeline / capacity / compute / accuracy / code-review | 把性能、精度、容量、bubble、硬件下界和 PR 风险转化为可验证结论 |
| Supporting Knowledge | `model-pr-optimization-history`、`kernel-pilot`、`references/`、`humanize/` | 保存历史 PR、kernel 实验、artifact schema、优化 ledger 和 lineage |

## 核心工作流

很多 NPU serving 优化失败，不是因为没有想法，而是证据链断了：

- baseline 没有 warmup，或者跑在被污染的设备上；
- 直接把 profiling trace 当作正式性能结果对比；
- 只从 evalscope accept rate 推断 MTP 是否真正启用；
- 只看少量 prompt 判断精度，没有 bad cases 或 A/B 数据集；
- PR 修复没有保留 build、UT、accuracy、performance 和 profiling artifacts。

本仓库用六个阶段来避免这些问题：

```text
Phase 0   Target and environment
Phase 0.5 Historical model knowledge
Phase 1   Fair baseline
Phase 2   Gap assessment
Phase 3   Evidence collection
Phase 4   Optimization plan
Phase 5   Research -> Learn -> Code -> Review -> Validate -> Record
Phase 6   Final record
```

这个闭环借鉴了 [PolyArch/humanize](https://github.com/PolyArch/humanize)
中的 RLCR discipline，但本仓库不是 Humanize RLCR 实现本身。在 Humanize 中，
RLCR 表示 Ralph-Loop with Codex Review：实现工作需要被独立 review，并反馈到下一轮迭代。
在本仓库中，xLLM NPU 工作流在这个 review loop 上扩展了 benchmark、profiling、accuracy
和 record-keeping 门禁。

完整流程见 [`docs/npu-ai-coding-standard-workflow.md`](docs/npu-ai-coding-standard-workflow.md)。

## Skills

| 任务 | 起点 | 需要时补充 |
|---|---|---|
| 启动服务、跑性能或精度评测 | [`xllm-npu-eval-runner`](skills/xllm-npu-eval-runner/SKILL.md) | 公平跨框架对比时使用 `xllm-npu-benchmark` |
| 优化 TPOT、TTFT、TPS 或吞吐 | [`xllm-npu-sota-loop`](skills/xllm-npu-sota-loop/SKILL.md) | Phase 3 根据症状选择 profiler、pipeline、capacity、compute 或 accuracy skill |
| 比较 xLLM、vLLM-Ascend、SGLang NPU | [`xllm-npu-benchmark`](skills/xllm-npu-benchmark/SKILL.md) | 保留失败候选和启动命令 |
| 解释 profiling 瓶颈 | [`xllm-npu-profiler`](skills/xllm-npu-profiler/SKILL.md) | decode bubble 或 rank skew 使用 pipeline analysis |
| 分析 prefill/decode 边界 | [`xllm-npu-pipeline-analysis`](skills/xllm-npu-pipeline-analysis/SKILL.md) | 需要硬件下界时加入 compute simulation |
| 估算内存和 serving 容量 | [`xllm-npu-capacity-planner`](skills/xllm-npu-capacity-planner/SKILL.md) | crash 或 OOM 时加入 incident triage |
| 估算 FLOPs、MFU 和理论下界 | [`xllm-npu-compute-simulation`](skills/xllm-npu-compute-simulation/SKILL.md) | workload 和模型 shape 明确后使用 |
| 定位乱码输出或精度回归 | [`xllm-npu-accuracy-debug`](skills/xllm-npu-accuracy-debug/SKILL.md) | 不清楚引入 commit 时使用 bisect |
| 定位 crash、OOM、图模式或 HCCL 事故 | [`xllm-npu-incident-triage`](skills/xllm-npu-incident-triage/SKILL.md) | 保存 replay 命令和原始日志 |
| Review NPU 相关 PR | [`xllm-npu-code-review`](skills/xllm-npu-code-review/SKILL.md) | 同时检查目标仓库自己的 agent rules |
| 迁移外部或实验性算子 | [`xllm-npu-op-migration`](skills/xllm-npu-op-migration/SKILL.md) | 只有新 kernel 被证明必要时才使用 `kernel-pilot` |
| 查询历史模型优化经验 | [`model-pr-optimization-history`](model-pr-optimization-history/SKILL.md) | 学到可复用经验后更新 dossier |
| 尝试 kernel-level 优化 | [`kernel-pilot`](kernel-pilot/SKILL.md) | 先用 profiling 证明 kernel 是瓶颈 |

## 示例任务

运行 xLLM 性能和精度评测：

```text
Use xllm-npu-eval-runner to start a Qwen3-32B xLLM service,
run evalscope with 5k input / 50 output / temperature=0,
and save manifest, metrics.json, report.md, and raw evalscope artifacts.
```

公平比较多个框架：

```text
Compare xLLM, vLLM-Ascend, and SGLang NPU on A3 NPUs.
Use the same model, workload, sampling parameters, and SLA.
Tune each framework independently and output summary, candidates, and winning commands.
```

诊断 TPOT 回归：

```text
Run warmed-up baseline/current performance tests.
Collect decode-focused profiling with xllm-npu-profiler.
Inspect the hostbound gap between replaceToken and the next GatherV2.
Produce a validated optimization candidate.
```

运行端到端优化闭环：

```text
Use xllm-npu-sota-loop:
Phase 0 records the environment and target.
Phase 0.5 queries model-pr-optimization-history.
Phase 1 establishes a fair baseline.
Phase 3 collects profiling evidence.
Phase 5 applies one patch per round.
Each round reruns accuracy, performance, and profiling when needed.
The final result is recorded in humanize ledgers and model PR history.
```

## 证据规范

正式结论应包含：

- run manifest；
- 启动命令、框架 commit 和 submodule 状态；
- 模型、tokenizer、dtype、硬件、workload、采样参数和 SLA；
- 原始 benchmark 输出和归一化 summary；
- profiling 用于诊断时的 profiling report；
- 可能影响正确性时的 accuracy report；
- 最终结论、已知风险、失败尝试和后续工作。

可优先使用这些共享规范：

| 规范 | 用途 |
|---|---|
| [`run-manifest-template.md`](references/run-manifest-template.md) | commit、环境、模型、启动命令、workload、artifact 路径 |
| [`perf-artifact-schema.md`](references/perf-artifact-schema.md) | TTFT、TPOT、TPS、warmup、采样参数、server-side counters |
| [`accuracy-artifact-schema.md`](references/accuracy-artifact-schema.md) | 原始预测、失败样例、分数、验证等级 |
| [`profiling-artifact-schema.md`](references/profiling-artifact-schema.md) | msprof 采集、五表分析、timeline notes、inconclusive 规则 |

## 环境要求

- Huawei Ascend 910B3 / A3 NPU，并包含 Ascend 910B / A2 兼容说明；
- 与目标框架兼容的 CANN / HDK driver；
- 至少一个 OpenAI-compatible serving 框架：xLLM、vLLM-Ascend 或 SGLang NPU；
- 用于正式评测和诊断的 evalscope、msprof / MindStudio profiling 工具；
- 能加载本地 skills 的 Codex、Claude Code、opencode 或其他 agent runtime。

## 仓库结构

```text
AGENTS.md                       Codex / opencode / 通用 agent 项目规则
CLAUDE.md                       Claude Code guardrails，与 AGENTS.md 保持同步
INSTRUCTIONS.md                 给 agent 和用户的简短本地说明
README.md                       默认英文入口文档
README_zh.md                    中文入口文档
docs/                           通用 NPU 工作流文档
skills/                         核心过程化 agent skills
prompts/                        可复制的任务 Prompt
references/                     共享 schemas、规格和可复用规则
model-pr-optimization-history/   历史模型和 PR 知识
humanize/                       run ledger contract
kernel-pilot/                   kernel 实验 helper
patches/                        最小 patch 或迁移说明
tests/                          仓库卫生和 schema smoke tests
```

## 贡献指南

- 把可复用经验沉淀为 skills、references、schemas、prompt 模板或 model history entries。
- 公共入口文档保持通用；模型相关经验放到 `model-pr-optimization-history/` 或 skill `references/`。
- 能解释未来决策的失败尝试要保留。
- 不要提交本地路径、私有 IP、私有数据集名称、凭据或非公开生产日志。
- 不要把 smoke 结果包装成正式性能或精度结论。
- 添加新框架时，将通用 NPU evidence layer 和 framework adapter layer 分开。

## License

当前尚未添加 license 文件。在面向更广泛外部复用宣传前，应先补充项目 license。
