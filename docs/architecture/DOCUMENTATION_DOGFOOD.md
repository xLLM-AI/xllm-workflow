# 文档可用性 Dogfood

日期：2026-07-12

以下是三个隔离、有限范围的公开文档定性 probe，不是一般化 usability 分数，也不验证 runtime routing。

## 方法

每个 reader 只获得一个角色，只能使用公开 README/docs 与其直接链接的 public skill 文档。Reader 不读取 PR14 设计、tests 或 catalog 源文件，不运行 workflow 命令，也不修改文件。

## Probe 1：首次性能优化用户

### 答案

从根 task 表选择 `xllm-npu-sota-loop`。初始化 workspace、启动 agent、固定真实 experiment spec；SOTA 负责优化决策，`xllm-experiment-lifecycle` 负责 run 状态与 evidence。随后建立 warmed baseline、profiling、通过 Big-Rock gate、逐假设 A/B，最后验证并 finalize。

### 跟随文档

1. `README.md`
2. `docs/getting-started.md`
3. `skills/README.md`
4. `skills/xllm-npu-sota-loop/SKILL.md`
5. `skills/xllm-experiment-lifecycle/SKILL.md`
6. `docs/npu-ai-coding-standard-workflow.md`

第一页即可找到主入口；建立完整操作心智模型需要四到六页。

### Dead end 或歧义

没有 blocking dead end。剩余成本来自操作深度：prerequisites、填好的真实 spec、预期成功 artifacts，以及初始化到 baseline 的完整顺序仍分布在详细文档中。部分核心 skill 是中文，而英文 landing page 是英文；这些是记录的限制，不是 routing/taxonomy 缺陷。

## Probe 2：Operator 工作流

### 答案

- 仅服务 lifecycle：`xllm-npu-server-manager`。
- 公平 benchmark 或可发布结论：`xllm-npu-benchmark`。
- Runtime 或 build 事故：`xllm-npu-incident-triage`。

Benchmark 与 incident 从根 task 表一跳可达。Service-only 原本需要绕到 `skills/README.md`，现已在根 task 表与 docs hub 中直接链接。

### Dead end 或歧义

修复导航后没有 blocking dead end。详细 skill 仍要求理解委托：benchmark 可能补采数据，incident replay 可能需要 build-gate artifacts，远程服务可以显式委托 SSH。这些过程边界不在 landing page 重复展开。

## Probe 3：Skill 维护者

### 答案

遵循八步维护流程：判断 skill/script；定义合约；新增或更新 `SKILL.md`；更新 catalog taxonomy 与 presentation；routing 语义变化时更新 cases；生成两个派生视图；refresh 对应安装模式；验证并执行相应 bounded probe。

不得手工编辑 `skills/README.md` 或 `docs/architecture/skill-map.md`。

### 跟随文档

1. `README.md`
2. `docs/README.md`
3. `docs/maintainers/adding-or-changing-a-skill.md`
4. 生成的 skill 与 architecture 视图用于确认

完整流程集中在一个 maintainer guide。Docs hub 指向该指南而不是 renderer 源码，指南也提供明确的 refresh mode 决策表。

### Dead end 或歧义

没有 blocking dead end。剩余限制包括：没有单独的 rename/alias 批准流程、全新 internal policy 文件模板，以及每个数量断言的 copy-ready 命令；full validation 仍覆盖这些合约。

## 结论

- Blocking navigation dead ends：**0**。
- 新用户主入口选择：**1 页**。
- Operator 主入口选择：**1–2 页**。
- Maintainer canonical workflow：**从根目录 3 页，一个集中指南**。
- Canonical ID、目录、routing description 与 invocation policy 变化：**0**。

这些 probe 仅支持“三个被测角色可以沿新入口完成导航”的 bounded 结论，不宣称广泛的文档可用性准确率。
