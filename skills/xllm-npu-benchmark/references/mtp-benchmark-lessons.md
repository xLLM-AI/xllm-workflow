# MTP Benchmark Lessons

This reference keeps historical Qwen3.5 MTP benchmark lessons out of the main
skill entry. Use it only when the current task is about MTP/speculative decoding
or reproducing the recorded Qwen3.5 cases.

## Environment Hygiene

- Performance conclusions require a clean target device set. Idle AICore near
  0% is not enough if HBM is still occupied by stale contexts.
- If `npu-smi info` shows PIDs that cannot be found by `ps`, treat the run as
  contaminated until the context is cleared or another card set is used.
- Evalscope formal runs must include request-level warmup. Historical runs
  without explicit warmup are useful as context, not final PR evidence.

## MTP Enablement Gate

Qwen3.5 checkpoints can contain native MTP weights, but xLLM serving requires an
exported draft model directory before a run can be called external-draft MTP:

```bash
python3 tools/export_mtp.py \
  --input-dir <model-root>/Qwen35-27B \
  --output-dir <model-root>/Qwen35-27B-mtp \
  --model-type qwen3_5
```

Minimum evidence:

- The draft directory contains `mtp_layer_parameters.safetensors`.
- The draft config `model_type` is `qwen3_5_mtp`.
- Startup includes `--draft_model <model-root>/Qwen35-27B-mtp`,
  `--draft_devices="npu:<rank>"`, and `--num_speculative_tokens N`.
- Rank logs show the draft model path, draft devices, and speculative decode
  enabled with MTP.

Do not use evalscope `Spec Accept Rate` alone as proof that external MTP is
active. Evalscope derives this value from streaming chunk structure. Formal MTP
reports must also save xLLM `/vars` deltas for:

- `speculative_num_accepted_tokens_total`
- `speculative_num_draft_tokens_total`

## Recorded Qwen3.5-27B Lessons

Representative random 20k input / 1k output, TP=4, single-concurrency scan:

| Config | TTFT (ms) | TPOT (ms) | Output TPS | Decoded Tok/Iter | Accept Rate |
|---|---:|---:|---:|---:|---:|
| no MTP | 2507.1 | 18.67 | 46.39 | 1.01 | 1.4% |
| MTP=1 | 2566.2 | 17.18 | 49.69 | 1.88 | 46.8% |
| MTP=2 | 2524.0 | 15.16 | 55.35 | 2.64 | 62.1% |
| MTP=3 | 2524.8 | 12.05 | 66.82 | 3.21 | 68.8% |
| MTP=4 | 2623.8 | 13.25 | 61.49 | 3.57 | 72.0% |
| MTP=5 | 2585.0 | 14.62 | 56.83 | 3.38 | 70.4% |

Lessons:

- For this long-input, long-output single-concurrency workload, MTP=3 was best.
- MTP=4/5 improved apparent accept rate but lost end-to-end throughput because
  draft/verify overhead increased.
- MTP mostly improves decode/TPOT. TTFT is dominated by prefill for long prompts.
- Higher MTP depth increases reserved linear cache; check HBM and KV blocks
  before using it for higher concurrency.

## PR #1541 Minimal Draft-Prepare Lesson

A minimal draft-preparation overlap attempt showed that moving only metadata
and CPU/device preparation earlier did not prove a stable speedup over the
historical MTP=3 baseline.

Key lesson:

- Work that depends on target logits, embeddings, or accepted prefix cannot be
  safely dispatched early without a commit/rollback design.
- Pure metadata preparation has limited upside and can add host overhead.
- Restore PR movement only after same-binary A/B and profiling prove stable
  benefit.

## Chunked Prefill Trap

`--enable_chunked_prefill=true --max_tokens_per_chunk_for_prefill=256` does not
guarantee that a single prefill request is split into 256-token chunks. If no
decode request competes for the budget and `prompt_len < max_tokens_per_batch`,
the scheduler can still process the full prompt in one step.

To verify chunking:

- Compare 20k input / 1 token output profiling with chunk on/off.
- Check counts for `MatMulV3`, `FusedInferAttentionScore`, and HCCL kernels.
- To force chunking, increase concurrency or lower `max_tokens_per_batch`.
