# 文档中心

从这里查找当前操作指南。`docs/pr12/` 与 `docs/pr14/` 保存设计记录，不是默认工作流入口。

## 从这里开始

- [入门指南](getting-started.md)：安装 skills，并完成一次合成 lifecycle。
- [标准 NPU AI Coding 工作流](npu-ai-coding-standard-workflow.md)：证据驱动阶段与审查门禁。
- [Skill 能力索引](../skills/README.md)：按角色或领域选择 canonical 入口。

## 执行工作流

- [实验生命周期](../skills/xllm-experiment-lifecycle/SKILL.md)
- [性能优化](../skills/xllm-npu-sota-loop/SKILL.md)
- [仅服务生命周期](../skills/xllm-npu-server-manager/SKILL.md)
- [混合评测](../skills/xllm-npu-eval-runner/SKILL.md)与 [benchmark 审查](../skills/xllm-npu-benchmark/SKILL.md)
- [Profiling](../skills/xllm-npu-profiler/SKILL.md)、[pipeline 分析](../skills/xllm-npu-pipeline-analysis/SKILL.md)与[事故诊断](../skills/xllm-npu-incident-triage/SKILL.md)
- [算子迁移](../skills/xllm-npu-triton-migration/SKILL.md)与 [runtime 接入](../skills/xllm-npu-xllm-ops-integration/SKILL.md)

## 理解系统

- [仓库与证据地图](architecture/repository-map.md)
- [生成的 Skill 架构地图](architecture/skill-map.md)
- [IO schemas 与示例](../reference/io_specs/)
- [模型与 PR 历史](../reference/pr_history/)

文档统一使用以下支持标签：

- **完整支持：** xLLM on Ascend 的完整工作流。
- **实验性 adapter：** 已声明的构建或证据 adapter，不代表框架完全可互换。
- **仅 artifact 分析：** 可分析已有 artifacts，但不宣称端到端 serving 支持。
- **内部 / 仅显式调用：** 不能成为隐式主路由。

## 维护仓库

- [新增或修改 Skill](maintainers/adding-or-changing-a-skill.md)
- [确定性脚本](../scripts/README.md)
- [Catalog 与生成文档维护流程](maintainers/adding-or-changing-a-skill.md#6-生成文档)
- [Agent 约束与路由合约](../AGENTS.md)

## 设计历史

- [PR12 taxonomy 与 routing 记录](pr12/PLAN.md)：历史设计与验证证据。
- [PR14 信息架构方案](pr14/PLAN.md)：本次导航工作的原始设计基线。

历史记录继续保持链接稳定；当前操作指南从上面的分类入口访问。
