# Capacity Log Patterns

Use this reference when reading xLLM/vLLM-Ascend/SGLang startup logs for memory
and request capacity.

## Common Signals

| Signal | Meaning |
|---|---|
| `KV blocks` / `num_gpu_blocks` / `num_npu_blocks` | Available KV cache blocks |
| `block_size` | Tokens per KV block |
| `max_model_len` | Maximum sequence length considered by scheduler/cache |
| `reserved_linear_bytes` | Speculative/MTP linear cache reserve |
| `max_memory_utilization` | HBM fraction available to the serving runtime |
| `xTensor` / `memory pool` | Runtime allocator reserve and fragmentation |
| `workspace` / `ATB` / `graph` | Runtime or graph execution reserve |
| `OOM` / `aclrtMalloc` failure | Hard allocation failure |

## Capacity Questions

- Is the service limited by HBM, KV blocks, max batch tokens, or max sequences?
- Does MTP/speculative decoding reduce KV blocks or reserve too much linear cache?
- Does increasing `max_memory_utilization` help, or is workspace/fragmentation the limiter?
- Does `block_size` waste capacity for the target request lengths?
- Is the benchmark comparing configurations with the same capacity headroom?

## Report Rules

- Quote only short log snippets; keep raw logs in artifacts.
- If logs do not expose enough information, mark capacity as `inconclusive`.
- Never recommend a performance benchmark on a configuration that is already at
  OOM risk without recording that risk in the manifest.
