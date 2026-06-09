# LLM FLOPs Formulas

These formulas are directional. Validate with profiling before making a final
optimization claim.

## Dense Transformer

Approximate per-token layer cost:

```text
QKV projection:       2 * hidden * (q_dim + k_dim + v_dim)
Attention scores:    2 * heads * seq_len * head_dim
Attention values:    2 * heads * seq_len * head_dim
Output projection:   2 * hidden * hidden
MLP up/gate/down:    depends on architecture, often ~6 * hidden * intermediate
```

Prefill cost grows with sequence length and attention matrix size. Decode cost
is usually dominated by projections, MLP, and attention over cached context.

## MFU

```text
MFU = estimated_flops / (elapsed_seconds * peak_flops)
```

Report:

- Model FLOPs estimate.
- Profiling elapsed device time.
- Hardware peak used.
- MFU percentage.
- Missing terms and assumptions.

## What-If

Useful what-if dimensions:

- TP: reduces per-rank compute but adds communication.
- Batch/concurrency: improves compute utilization but consumes KV cache.
- MTP/speculative decoding: can reduce decode steps but adds draft/verify cost.
- Output length: changes decode dominance and amortizes TTFT differently.
