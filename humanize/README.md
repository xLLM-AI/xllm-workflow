# humanize/ — 经验飞轮

本目录是动态经验池，Agent 在排障与调优过程中自动积累踩坑经验，
使工作区"越用越聪明"。

## 目的

- 保存经验证的优化结论、排障经验和反复出现的坑点
- 为后续 Agent 执行同类任务时提供参考
- 用运行中验证的教训补充 `reference/` 中的静态知识

## 写入规则

- 仅写入**经验证的教训**（不写猜测、不写假设）
- 每条经验必须包含：场景、根因、解法、验证方式
- 具体 ledger 文件（attempt-ledger、optimization-ledger、source-idea-ledger、lineage.jsonl）
  在每次运行根目录 (`runs/`) 下生成，不存放于此
- 仅持久价值的教训才会回流到本目录

## Ledger 契约

具体 ledger 存放在每次运行根目录下：

```text
<run-root>/humanize/
  attempt-ledger.md
  optimization-ledger.md
  source-idea-ledger.md
  lineage.jsonl
```

持久经验回流到仓库：

- 模型特有风险与收益 → `reference/pr_history/`
- profiling 经验 → skill references 或 `reference/pr_history/`
- 可复用的 artifact 字段 → `reference/io_specs/`
- 可复用的工作流 → `skills/`

这样防止过期的本地实验路径变成全局指导，同时保留每次运行的
证据循环记录。

## 当前状态

（目录初始为空。内容由 Agent 在实际排障与调优过程中逐步填充。）