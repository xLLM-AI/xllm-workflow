# MTP Transpose Elimination Evidence Case

Use this case when profiling an MTP / speculative-decoding path shows a large
number of transpose, reshape, pack, slice, or small layout-conversion kernels.

The reusable lesson is not "remove every transpose". The lesson is to prove that
a layout conversion is redundant, remove it in the narrowest model/operator path,
then validate with accuracy, profiling, and formal benchmark evidence.

## Symptom

MTP improves throughput over baseline, but profiling shows a visible amount of
device time and kernel launch count in MTP-only layout kernels.

Example evidence shape:

| Observation | Meaning |
|---|---|
| Transpose kernel appears only in MTP run | likely speculative verify or draft path overhead |
| call count scales with decode steps | per-step layout conversion, not one-time setup |
| accept rate unchanged across variants | optimization should preserve speculative behavior |
| TPOT changes more than TTFT | issue is likely decode/verify-loop overhead |

## Investigation

Compare at least two profiles:

```text
baseline
MTP enabled
MTP enabled + candidate layout change
```

Use the same model, commit base, NPU count, input/output lengths, sampling
parameters, and warmup. Do not use profiling timing as the final performance
number; use it to explain the benchmark delta.

Checklist:

- confirm the transpose kernel is absent or much smaller in the non-MTP baseline;
- map the kernel to source using op name, stack, wrapper, or model path;
- check whether tensors are converted from `[B, C, T]` to `[B, T, C]` and back;
- check whether a weight transpose is recomputed every step;
- verify that the consumer kernel can accept a stable alternate layout.

## Narrow Fix Shape

Prefer a local model/operator fix over a scheduler-wide change:

- cache one-time transposed weights during model initialization or first use;
- keep the MTP verify path in one layout instead of round-tripping layouts;
- update the wrapper contract if the kernel already naturally consumes the
  alternate layout;
- add shape/layout assertions near the boundary.

Avoid:

- changing layout globally for unrelated prefill/decode paths;
- removing a transpose without checking the target kernel ABI;
- bundling layout cleanup with speculative-token bookkeeping changes.

## Evidence Standard

A successful case should have three independent signals.

### Accuracy

Run a deterministic fixed-prompt smoke before any performance claim. If this
path previously had precision regressions, add a small dataset slice.

### Profiling

Report call count and device time for the targeted layout kernel before and
after.

Example format:

| Kernel family | Before calls / time | After calls / time | Delta |
|---|---:|---:|---:|
| MTP transpose variant | 14,400 / 207.8 ms | 960 / 17.3 ms | -93.3% calls |

### Formal Benchmark

Run a warmed-up benchmark outside profiler collection.

Example format:

| Metric | Before | After | Delta |
|---|---:|---:|---:|
| output throughput | 36.11 tok/s | 39.54 tok/s | +9.5% |
| TPOT | 24.2 ms | 21.9 ms | -9.5% |
| accept rate | 47.7% | 47.7% | unchanged |

The exact numbers are hardware, model, and workload dependent. Keep the table
format, not the numbers, as the reusable contract.

## Risk Checks

Layout optimizations are correctness-sensitive. Check:

- BF16/FP16 accumulation and cast points did not change;
- graph capture and eager paths both use the same layout contract;
- TP>1 does not shard the layout dimension differently;
- MTP `num_speculative_tokens > 1` is tested if supported;
- server-side speculative counters still match expected accept/draft behavior.

## Recording

Write the case into the run root:

```text
$RUN_ROOT/humanize/optimization-ledger.md
$RUN_ROOT/profiles/<variant>/triage.md
$RUN_ROOT/benchmark/<variant>/summary.md
```

Promote the lesson to `reference/pr_history/` only after the fix has both
accuracy and benchmark evidence.

