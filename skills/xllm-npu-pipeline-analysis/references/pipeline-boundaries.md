# Pipeline Boundary Notes

## Decode Boundary Examples

For xLLM decode-step hostbound analysis, useful intervals include:

```text
previous token replacement / sampler result
  -> next graph replay parameter preparation
  -> GatherV2 / attention input gather
  -> attention / MLP kernels
  -> argmax or sampler
  -> replace token
```

If the next `GatherV2` starts late, inspect:

- Graph replay parameter preparation.
- `CustomPagedAttentionOperation::Setup`.
- Small D2D/H2D/D2H copies.
- `aclnnInplaceCopy`, `aclnnInplaceFillScalar`, `aclnnCast`.
- `aclmdlRIExecuteAsync`.
- `StreamWaitEvent` or stream synchronization.

## Rank Skew Questions

- Is one rank consistently later at HCCL collectives?
- Does rank skew start in prefill, decode, or postprocess?
- Are all ranks using the same visible-device order and model shard layout?
- Did profiling attach to only one rank or all ranks?

## Reporting Rules

- Do not claim a user-visible speedup from a trace alone.
- Always connect the candidate fix to a measurable TPOT/TTFT/TPS metric.
- If stage boundaries are ambiguous, mark the section `inconclusive`.
