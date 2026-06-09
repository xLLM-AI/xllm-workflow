# MTP Profiling Lessons

This reference stores historical Qwen3.5 MTP profiling findings. Load it only
when the task specifically involves MTP/speculative decoding, transpose
elimination, accept-mask optimization, or draft scheduling overlap.

## MTP Profiling Checklist

| Dimension | Healthy Evidence | Bad Signal |
|---|---|---|
| MTP enabled | Rank logs show draft model path, draft devices, and speculative decode | Only `--num_speculative_tokens` or evalscope accept rate |
| Draft weights | Exported `*-mtp` directory with MTP tensors | Main model directory reused as draft |
| `num_speculative_tokens` | Chosen by workload scan | Chosen only by higher accept rate |
| Accept rate | Server `/vars` accepted/draft delta is stable | Evalscope-only accept rate |
| Decoded Tok/Iter | Bounded by `num_speculative_tokens + 1` unless chunk aggregation is explained | Much larger than the configured speculative depth |
| Memory | Reserved linear cache and KV blocks leave headroom | MTP depth increases reserve enough to hurt capacity |

## Representative TP=4 / MTP=3 Trace Lessons

Decode-focused traces showed:

- MatMul and communication dominated device time.
- TP=4 decode had meaningful allreduce/allgather cost.
- MTP accept/verify logic added many small ops and host synchronization.
- Transpose was a visible local hotspot, but the structural issue was that MTP
  spec-verify did not reuse the non-MTP causal-conv path.

Optimization order:

1. Compare non-MTP decode and MTP spec-verify paths before editing local
   transpose calls.
2. Treat cached transpose removal as local mitigation.
3. Prefer structural reuse of the non-MTP `causal_conv1d` contract, or an
   equivalent fused spec-verify causal-conv kernel.
4. For accept/verify small ops, prefer a fused kernel over Torch-level rewrites.

## Transpose Elimination Lesson

The effective local mitigation was:

- Keep spec-verify input/output in `[B,T,C]`.
- Cache pre-transposed conv weight instead of transposing every step.
- Avoid unnecessary round-trip `transpose(1,2)`.

Observed directionally useful result:

| Metric | Before | Transpose-opt | Direction |
|---|---:|---:|---|
| Transpose time | 505.08 ms | 205.86 ms | lower |
| Transpose calls | 36,701 | 12,604 | lower |
| Device total | 5310.22 ms | 5005.63 ms | lower |
| Decode TPOT | 10.62 ms | 9.90 ms | lower |
| Output TPS | 66.25 | 69.70 | higher |

Precision smoke used GSM8K `limit=10` and completed without service errors.
For formal precision conclusions, use the accuracy artifact schema.

Important caveat:

- PR descriptions must not claim causal-conv path reuse if the code only removes
  local transpose overhead.
- `cache_indices` and `num_accepted_tokens` are dynamic graph replay inputs for
  MTP verify. Host vectors or `IntArrayRef` can be captured as stale attributes
  and corrupt conv cache state.

## Accept-Mask Small-Op Counterexample

Torch-level rewrites of the rejection sampler mask were not useful:

- `cumprod` reduced one pattern but introduced a heavier prefix scan.
- A bool-prefix rewrite avoided dtype conversion but still used multiple
  slice/logical/cat ops.
- Neither beat the transpose-opt baseline.

Future work should use a true fused kernel or reuse an existing rejection-sample
kernel path.

## Draft-Prepare Overlap Lesson

A naive P0 design enumerated all possible accepted-prefix futures while target
validation was still running. It was correct in principle but too expensive on
the host path.

The useful low-risk subset was to prepare only work that does not depend on
target output:

- Base input device copy.
- CPU views of static decode fields.
- Original input token cache.

True async draft dispatch needs a draft KV commit/rollback or double-buffer
design. Without that, early draft compute risks breaking consistency between
target accepted prefix and draft KV state.
