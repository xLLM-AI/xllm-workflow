# Model PR Dossier Card Schema

每个模型档案应能回答“历史改过什么、风险在哪里、下次优化前先看哪里”。

## Required Fields

| 字段 | 说明 |
|---|---|
| framework | `xllm` / `vllm-ascend` / `sglang` |
| model_family | 模型族，例如 `Qwen3.5`、`DeepSeek-V3` |
| scenario | 适用场景，例如 MTP、sampling、VLM、MoE、long prefill |
| related_prs | PR 号、commit 或本地 patch 名称；未知时写 `TBD` |
| touched_paths | 关键代码路径、算子、配置或脚本 |
| optimization_intent | 这次改动想解决什么性能或精度问题 |
| validation | 精度、性能、profiling、UT 或编译证据 |
| risks | 已知风险、反例、回退条件 |
| next_checks | 后续遇到同类问题时优先检查什么 |

## Quality Rules

- 不把临时机器路径、私有数据集名、账号、端口或密钥写进公开档案。
- 结论必须区分“已验证”“推测”“待验证”。
- 性能数据必须说明是否 warmup、是否 profiling run、是否同 commit A/B。
- MTP/speculative 场景必须记录服务端真实 counter，而不能只依赖压测工具推导的接受率。
- 精度回归必须记录验证等级：单 prompt、固定小集、task 全量或全量评测集。
