# Qwen3.5 Chunked Prefill Init-State Accuracy Case

Use this case when Qwen3.5 or another hybrid-attention model produces garbled
output after enabling chunked prefill, token-flat prefill, graph replay, or a
new fused GDN / SSM kernel.

This is a reusable debugging pattern, not a model-specific patch recipe. The
important lesson is to localize the first divergent tensor before changing
scheduler, graph, or kernel code.

## Symptom

The model runs without a crash, but generated text becomes unreadable or
accuracy drops after chunked prefill is enabled. Ordinary short-prompt decode
may still look correct.

Typical trigger shape:

| Field | Example |
|---|---|
| Model family | Qwen3.5 / Qwen3 Next style hybrid attention |
| Layer type at risk | Gated Delta Net / linear attention |
| Feature | chunked prefill or token-flat prefill |
| Prompt length | long enough to split into multiple chunks |
| Failure mode | output divergence starts after the first continued chunk |

## Why This Happens

Full attention usually carries cross-chunk history through KV cache. Linear
attention / GDN carries history through a recurrent state. If the recurrent
state layout, indexing, or update timing differs between chunks, the next chunk
can start from the wrong state even when q/k/v/g/beta inputs match.

The risky tensor is often shaped like:

```text
[batch, num_heads, head_size, head_size]
```

The last two dimensions can have identical statistics after a transpose, so min,
max, mean, and dtype checks may all look correct while elementwise comparison
fails badly.

## Localization Pattern

Use a reference path such as GPU eager, torch fallback, vLLM-Ascend, or a known
good xLLM commit. Dump the same tensors from both sides with deterministic input
and fixed generation settings.

Recommended order:

1. Pick a prompt that forces at least three chunks.
2. Dump per-layer conv / GDN inputs and outputs in model execution order.
3. Confirm whether the first chunk exists on both sides.
4. Compare the second chunk onward, because continued chunks consume recurrent
   state.
5. At the first divergence, compare the GDN inputs separately:
   `q`, `k`, `v`, `g`, `beta`, `initial_state`, output, and `final_state`.

Example finding:

| Tensor | Result | Interpretation |
|---|---|---|
| `q` | match | projection path is probably not the root cause |
| `k` | match | projection path is probably not the root cause |
| `v` | match | projection path is probably not the root cause |
| `g` / `beta` | match or tiny diff | gating path is probably not the root cause |
| `initial_state` | diverges | cross-chunk state handoff is the likely root cause |
| output / `final_state` | diverges | downstream effect of bad state |

If both `initial_state` tensors have the same shape and statistics, explicitly
test layout transforms:

```python
np.allclose(xllm_init_state, ref_init_state)
np.allclose(xllm_init_state, ref_init_state.transpose(0, 1, 3, 2))
```

## Root-Cause Class

This case belongs to the "state layout drift" class:

- cross-chunk `final_state -> initial_state` handoff uses the wrong layout;
- a fused GDN kernel returns `final_state` in a different convention from the
  next chunk's `initial_state`;
- graph replay uses stale or padded host parameters for state indices;
- model code and fallback/reference code disagree on row/column semantics for
  `[head_size, head_size]`.

## Fix Shape

Do not add a transpose blindly. First decide which layout is the xLLM internal
contract and make the producer and consumer agree.

Common fix shapes:

- normalize `final_state` before storing it into the recurrent-state cache;
- normalize `initial_state` when loading it for the next chunk;
- update the fused kernel wrapper contract and tests if the kernel layout is the
  real source of truth;
- ensure graph replay refreshes state indices and shape-dependent host params
  before each replay.

Avoid fixing only the failing prompt. The same state contract must hold for:

- first chunk, continued chunks, and final short chunk;
- TP=1 and TP>1 when the state is sharded or indexed differently;
- graph and non-graph execution;
- MTP verify paths if they reuse chunked-prefill-like inputs.

## Validation

Minimum validation after the fix:

| Level | Required check |
|---|---|
| Tensor | first divergent `initial_state` now matches or matches the chosen layout contract |
| Smoke | deterministic prompt that previously produced garbled output is readable |
| Chunk | prompts with 1, 2, and 3+ chunks all pass |
| A/B | chunked prefill off vs on preserves output within accepted tolerance |
| Regression | run at least a small dataset slice when the original failure was data-dependent |

Record the case in the run artifact with:

- prompt length and chunk size;
- model commit and runtime flags;
- first divergent tensor name and layer/index;
- before/after tensor comparison result;
- final accuracy smoke and any dataset-slice result.

