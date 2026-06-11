# xLLM AI Coding Workflow

语言：[English](README.md) | [简体中文](README_zh.md)

面向昇腾 NPU 大模型推理优化的 agent-ready 工作流、Prompt、证据规范和参考知识库。
首个落地目标：[xLLM](https://github.com/jd-opensource/xllm)；公平基线：
[vLLM-Ascend](https://github.com/vllm-project/vllm-ascend) 和 SGLang NPU。

**本仓库可以处理的任务：**

1. **特性设计与开发** — 设计新的 NPU serving 特性，编写代码，通过 review-gated 证据闭环验证。
2. **问题定位与修复** — 定位精度回归、crash、OOM、图模式失败或 HCCL 问题，产出可复现证据和验证过的 patch。
3. **性能优化** — 建立公平基线，采集 profiling 证据，识别瓶颈，迭代逼近 TPOT/TTFT/TPS 目标并量化收益。

## 1 快速开始

### A. 安装 Skills

```bash
export AGENT_SKILL_DIR="${CODEX_HOME:-$HOME/.codex}/skills"   # Codex
# export AGENT_SKILL_DIR="$HOME/.claude/skills"               # Claude Code

mkdir -p "$AGENT_SKILL_DIR"
for skill_dir in skills/xllm-npu-*; do
  ln -sfn "$(pwd)/$skill_dir" "$AGENT_SKILL_DIR/$(basename "$skill_dir")"
done
```

### B. 选择 Prompt

从 [`prompts/`](prompts/) 复制模板，填入模型、硬件、框架、workload 和目标指标。

| Prompt | 场景 |
|---|---|
| [`sota-loop`](prompts/xllm-npu-sota-loop-prompts.md) | 端到端优化、TPOT/decode gap、MTP 验证 |
| [`eval-profiler`](prompts/xllm-npu-eval-profiler-prompts.md) | 服务启动、evalscope、profiling、容量/OOM |
| [`pr-fix`](prompts/xllm-npu-pr-fix-prompts.md) | PR 回归、review 回复、rebase、编译门禁 |
| [`op-migration`](prompts/xllm-npu-op-migration-prompts.md) | 算子迁移、torch_npu/Triton-Ascend/AscendC |

### C. 证据闭环

正式工作遵循 `target → baseline → profiling → patch → accuracy → performance → record`。
Skill 路由见 [AGENT.md](AGENT.md)，Phase 详情见 [docs/workflow](docs/npu-ai-coding-standard-workflow.md)。

## 2 目录一览

```text
AGENT.md            → Agent 系统提示（约束、Skill路由、目录说明）
CLAUDE.md           → Claude Code 引流至 AGENT.md
config.json         → 统一配置 SSOT（active / full_test / static）
prompts/            → 可直接复制的中文任务 Prompt 模板
skills/             → 11 个过程化 agent skill（评测、profiler、benchmark…）
reference/
   A  knowledge/    → 不可变领域规则（NPU 规格在 config.json static.npu_specs）
   B  code-style/   → C++/Python/NPU 代码风格约定
   C  io_specs/     → Artifact schema（manifest、perf、accuracy、profiling）
   D  pr_history/   → 模型 dossier 与 PR 历史（可通过 scripts/query.py 查询）
baseline/           → 性能验收标准
scripts/            → 跨 skill 共用确定性脚本
humanize/           → 经验飞轮（经验证的排障与调优教训）
docs/               → NPU AI Coding 工作流文档
tests/              → 仓库卫生与 schema 校验
code/               → 外部源码挂载（gitignored）
runs/               → 执行现场（gitignored）
```

**`config.json`** 是所有配置的唯一入口（SSOT）。包含三个区块：`active` 存放当前工作使用的模型、NPU 和 serving 参数；`full_test` 列出跨模型和跨框架的全面验证目标；`static` 存储不可变的硬件规格（NPU 峰值算力、带宽、HBM）。Skills 和脚本统一读取 config.json，不再硬编码。

**`reference/`** 是静态知识基石——不可变的领域规则，不会因单次运行而改变。Skills 从这里查询硬件限制、代码风格、artifact schema 和历史优化上下文。

**`humanize/`** 是经验飞轮——Agent 把经验证的排障教训写入此处，使工作区越用越聪明。具体 ledger 在运行根目录下生成，仅持久价值的教训回流到本目录。

**`scripts/`** 是确定性引擎——跨 skill 共用的自动化脚本，LLM 不得修改脚本逻辑，变更需人工审核。

**`skills/`** 包含 11 个过程化 agent skill，每个 SKILL.md 定义了执行流程、证据合约和本地 reference。Agent 加载与任务匹配的最小 skill 即可。

## 3 典型工作流

![xLLM AI Coding Workflow](docs/assets/xllm-ai-coding-workflow-zh.png)

证据驱动闭环：每次优化从可量化目标出发，采集可比数据，做一条可 review 的改动，
并留下可复现的 artifact。

## 4 贡献指南

1. **确定性能力写成脚本** — 任何可自动化的确定性逻辑（编译、评测、profiling 收集）应固化为 `scripts/` 下的脚本，禁止 LLM 修改脚本逻辑。
2. **可复用经验沉淀为 Skill** — 重复执行的标准工作流（如 benchmark 对比、PR review）封装为 `skills/` 下的 Skill，而非散落的零散笔记。
3. **踩坑经验与最佳实践沉淀到 humanize** — 经验证的排障教训、调优心得、反复出现的坑点写入 `humanize/`，使工作区越用越聪明。
4. **避免重复** — 配置、规范、提示词不多处重复；同一信息只保留一处，其他引用指向它（SSOT）。
5. **不提交本地路径、私有 IP、凭据或非公开日志。**

## 5 License

当前尚未添加 license 文件。在面向更广泛外部复用前，应先补充。