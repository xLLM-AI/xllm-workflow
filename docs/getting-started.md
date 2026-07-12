# 入门指南

本指南安装 canonical skills，并演示一个不使用 NPU 的合成实验 lifecycle。它不会启动模型服务，也不产生硬件性能结论。

## 1. 选择工作区模式

从 workflow 仓库初始化或复用 `code/xllm`，并把项目 skills 链接到 `.agents/skills`：

```bash
python scripts/init_xllm_workspace.py
```

如果从已有 xLLM checkout 启动 agent，把项目 skills 安装到所选 agent 目录：

```bash
python scripts/init_xllm_workspace.py --mode xllm --agent codex
```

安装器只发现 `skills/catalog.json` 声明的 canonical 目录。

## 2. 启动 Agent

仓库根目录模式：

```bash
codex
```

xLLM checkout 模式：

```bash
cd code/xllm
codex
```

Refresh 后应启动新 task，让 agent 获取最新 skill metadata。

## 3. 选择主工作流

- 新建或恢复 run 状态：`xllm-experiment-lifecycle`。
- 开放式 xLLM 优化：`xllm-npu-sota-loop`，run 状态委托 lifecycle 管理。
- 对 ready 服务执行一次性能测试：`xllm-npu-perf-runner`。
- 性能与精度混合评测并收集完整 artifacts：`xllm-npu-eval-runner`。

全部入口见 [Skill 能力索引](../skills/README.md)。

## 4. 创建合成 Lifecycle

复制 [`experiment.example.yaml`](../reference/io_specs/experiment.example.yaml)，设置本地 run root 与源码 checkout，并保持 `environment.require_npu: false`。然后遵循 [lifecycle skill](../skills/xllm-experiment-lifecycle/SKILL.md) 的 canonical 顺序：

```text
preflight -> run create -> specialist artifacts -> attempt add
          -> run validate -> export evidence -> gate all
          -> finalize -> retention review -> archive
```

`tests/test_lifecycle_skill_cli.py` 会通过真实 CLI subprocess 执行这条 lifecycle，但不会启动服务或使用 NPU。

## 5. 进入真实任务

真实 run 开始前必须固定 model、binary、checkout、hardware、workload、sampling 与 evidence level。遵循[标准工作流](npu-ai-coding-standard-workflow.md)，并保持支持边界：xLLM 是完整主路径；vLLM-Ascend 与 SGLang 仅限显式声明的 adapter 或 artifact scope。

## 验证仓库

```bash
python scripts/validate_skill_catalog.py
python scripts/render_skill_docs.py --check
pytest -q
git diff --check
```
