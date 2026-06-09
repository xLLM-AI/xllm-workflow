# Chunked Prefill Benchmark 注意事项

`--enable_chunked_prefill=true --max_tokens_per_chunk_for_prefill=256` 不一定意味着单请求 prefill 会被强制切成 256-token 多步执行。

在没有 decode 请求竞争且 `prompt_len < max_tokens_per_batch` 时，xLLM chunk scheduler 可能在 `handle_remaining_budget` 中把剩余 token budget 继续补给该 prefill，最终仍一次处理完整 prompt。

## 验证方法

- 使用长输入 / 短输出采集 prefill profiling，例如 20k 输入 / 1 token 输出。
- 对比 no-chunk 与 chunk 配置。
- 如果 `MatMulV3`、`FusedInferAttentionScore`、`hcom_allReduce_` 等关键算子 count 完全一致，说明 chunk 没真正发生。
- 要验证 chunk 收益，应增加并发、混入 decode，或降低 `--max_tokens_per_batch` 到 4096/8192 以强制多步 prefill。

## 报告要求

- 写清 chunk 参数和 `max_tokens_per_batch`。
- 写清 workload 是否包含 decode 竞争。
- 给出 profiling 算子 count 对比，而不只写 evalscope 端到端指标。
- 如果 chunk 未实际发生，结论标记为 `INCONCLUSIVE`，不要写 chunked prefill 收益。
