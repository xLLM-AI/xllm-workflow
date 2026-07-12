# PR14 当前导航审计

日期：2026-07-12
基线：`origin/main` 的 `6c66948ee62db132e30c5ec46fe582b3954919b5`，与 PR #13 tree 等价的 squash merge。

## 方法

公开文档修改前，三个隔离只读 reviewer 分别检查：首次性能优化用户、skill 维护者、skill 架构与生成文档可行性。

## Reader A：首次用户

原有路径可达，但需要在根 README、初始化、prompt、`AGENTS.md`、lifecycle 与专项 skill 之间进行约六次跳转。主要歧义是 `xllm-experiment-lifecycle` 控制面与 `xllm-npu-sota-loop` 优化入口的关系；`docs/` 缺少入口也让 `docs/pr12/` 容易被误认为当前操作指南。

审计还发现 SOTA prompt、标准 workflow 与 scripts guide 中存在旧示例不一致。这些内容记录为后续候选；PR14 不修改 skill routing description、invocation policy 或 runtime 行为。

## Reader B：维护者

原仓库没有把 skill/script 判断、`SKILL.md`、catalog、routing cases、refresh、双语导航、生成文档和验证串起来的单一指南。规则散落在 README、`AGENTS.md`、tests、initializer 与 PR12 历史中。需要一个 canonical maintainer guide，并明确生成文件与人工维护文件的边界。

## Reader C：架构与生成

Catalog 已负责 21 个扁平 canonical skill 的 discovery，因此可以安全增加 presentation metadata，而不改变 installer 或 routing。Role 与 exposure 应由 catalog 明确声明，避免 renderer 内维护第二份 ID mapping。生成器必须固定排序、使用稳定相对链接、不包含时间戳或本地路径，并提供只读 `--check`。

## Milestone 1–5 决策

1. 保持所有 canonical skill ID 与扁平目录不变。
2. Presentation 增加 `role_group` 与 `exposure`，仅服务人类导航。
3. Catalog schema 继续使用 version 1，但 validator 强制检查完整 presentation metadata。
4. 在没有 cycle gate 时称为 dependency graph，不夸大为 DAG。
5. 只生成 `skills/README.md` 与 `docs/architecture/skill-map.md`。
6. 新增一个文档中心、精简双语主页、repository map、getting started 与单一 maintainer workflow。
7. 把 PR12 标为设计历史并保持所有路径稳定。
8. 最终三个 usability probe 只作为 bounded qualitative checks，不宣称一般化准确率。
