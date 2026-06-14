# Qwen3.5 / Qwen3 Next Optimization Dossier

## Metadata

| Field | Value |
|---|---|
| framework | xLLM |
| model_family | Qwen3.5 / Qwen3.5-MoE / Qwen3 Next / Qwen3.6 |
| scenario | NPU model support / GDN / MTP / graph mode / VLM / PD / sampling postprocess |
| status | living dossier |

## Key Paths

| Path or Symbol | Why It Matters |
|---|---|
| `xllm/models/llm/qwen3_5.h` | Qwen3.5 model, checkpoint and MTP model definitions |
| `xllm/models/llm/qwen3_5_mtp.h` | Qwen3.5 MTP draft model entry |
| `xllm/models/llm/qwen3_next.h` | Qwen3 Next NPU model entry |
| `xllm/models/llm/qwen3_next_hybrid_base.h` | shared hybrid full-attention + linear-attention forward path |
| `qwen3_next_hybrid_decoder_layer_base` | common decoder layer base shared by Qwen3 Next and Qwen3.5 |
| `qwen3_next_attention` | Qwen3 Next/Qwen3.5 full-attention path, weight transform and mask risks |
| `qwen3_gated_delta_net_base` | shared gated delta network / conv1d / linear-state implementation |
| `MTPWorkerImpl::step_decode` | draft generation and target validation entry |
| `MTPWorkerImpl::run_validate` | target-model verify path; graph and chunk-prefill interactions surface here |
| `MTPWorkerImpl::update_decode_step_input` | position, KV length, accepted-token bookkeeping |
| `SpeculativeWorkerImpl::step` | target/draft orchestration boundary |
| `GraphPersistentParam::update` | decode graph persistent parameter update; must not be used for non-decode batches |
| `tools/export_mtp.py` | Qwen3.5/Qwen3.5-MoE MTP weight export and config rewriting |
| sampling postprocess path | top_p/top_k can introduce host sync and accuracy/perf risks |

## Timeline: Commit-Derived History

This table is derived from xLLM git history and should be updated when new PRs
land. It records intent and risk, not a full changelog.

| Date | PR / Commit | Area | What Changed | Next Checks |
|---|---|---|---|---|
| 2026-03-24 | #989 / `d1354441` | Qwen3 Next baseline | Added NPU Qwen3 Next model, attention, GDN, partial RoPE, RMSNorm, KV and state-dict support. | Validate model config parsing, KV cache shape, attention metadata and graph capture before optimizing derived Qwen3.5 paths. |
| 2026-03-25 | #1094 / `0f95a430` | Qwen3.5 baseline | Added Qwen3.5/Qwen3.5-MoE model and checkpoint support by sharing the Qwen3 Next hybrid base and adding Qwen3.5 GDN. | Treat Qwen3.5 as a Qwen3 Next-derived model; check shared base changes for both families. |
| 2026-03-27 | #1119 / `3011eb4c` | MTP draft | Added Qwen3.5/Qwen3.5-MoE MTP draft model and registry support. | Verify MTP model type mapping, draft vocab size, layer count and weight export. |
| 2026-04-08 | #1171/#1213 | graph state | Fixed Qwen3.5 GDN conv state indices for ACL graph. | Graph replay must update conv/linear state indices consistently for padded batches. |
| 2026-04-16 | #1259/#1280 | SSM cache | Initialized `ssm_cache` from config and fixed `g`/`beta` dimension order for Qwen3.5. | When outputs are readable but scores drop, inspect state cache type and tensor dimension order first. |
| 2026-04-21 | #1291 / `117430c9` | conv1d op | Updated `conv1d_update` for Qwen3 Next/Qwen3.5. | Compare op interface with GDN decode shapes and graph replay inputs. |
| 2026-04-21 | #1307 / `681f9c7b` | GDN gating | Optimized fused GDN gating for Qwen3.5 prefill/decode. | Profile both prefill and decode; fused gating changes can be shape-sensitive. |
| 2026-04-22 | #1315 / `1e48c1bd` | full attention | Added TileLang `split_qkv_rmsnorm_mrope` and integrated it into Qwen3.5 full-attention forward. | Keep a dataset-slice precision gate; fused QKV/RMSNorm/RoPE kernels can regress silently. |
| 2026-04-22 | #1262 / `f24d8232` | GDN fusion | Added NPU recurrent/chunk gated delta rule fusion operators for Qwen3.5/Qwen3 Next. | Compare recurrent state, chunk state and fallback torch path on the same shapes. |
| 2026-04-23 | #1329/#1330 | TP split kernel | Added and widened split-QKV/RMSNorm/MRoPE specializations for Qwen3.5/3.6 TP splits with runtime guards. | Check TP-specific enablement and unsupported-shape fallback. |
| 2026-04-25 | #1345 / `c1f83be4` | causal conv | Updated causal convolution 1D op for Qwen3.5/Qwen3 Next on NPU. | Validate conv state layout and padding, especially for graph/concurrent decode. |
| 2026-04-25 | #1348/#1341 | add_norm | Added add_norm fusion for Qwen3.5/Qwen3.5-MoE linear-attention layers. | Compare numerical tolerance with unfused norm and verify MoE/non-MoE variants. |
| 2026-04-26 | #1350/#1454 | token-flat prefill | Supported token-flat Qwen3.5 GDN prefill with correct recurrent state. | Check token-flat input packing and state indexing in ACL graph executor. |
| 2026-04-26 | #1353/#1489 | GDN decode refactor | Simplified Qwen3.5/Qwen3 Next GDN decode projection path. | Refactor touches shared base; run both Qwen3.5 and Qwen3 Next decode smoke. |
| 2026-04-26 | #1354/#1540 | VLM | Added Qwen3.5 VLM image/video input support. | Ensure VLM changes are carried when rebasing Qwen3.5 branches and do not break text-only MTP. |
| 2026-04-27 | #1357 / `fad91002` | conv weight | Optimized convolution weight processing for Qwen3.5. | Weight transform/reuse must be serialized or guarded; stale transforms caused later regressions. |
| 2026-05-07 | #1400 / `fd4e53bd` | Qwen3.6 weights | Prevented repeated Qwen3.6 weight adjustment. | Weight layout mutations must be idempotent and thread-safe. |
| 2026-05-12 | #1409 / `0b294d0e` | MTP target/verify | Added Qwen3.5 MTP speculative decoding: export, embedding cache, KV shape, attention metadata, graph executor and MTP worker changes. | Must validate MTP export, server counters, graph path, conv state and acceptance rate together. |
| 2026-05-14 | #1322 / `d56208c3` | conv1d fn | Updated `conv1d_fn` op for Qwen3 Next/Qwen3.5 on NPU. | Watch optional bias/state params and worker-side model input params. |
| 2026-05-18 | local `3f7c5f19` | graph perf | Skipped host tensor creation in graph mode to fix TPOT regression. | Search for `.cpu()`, `.item()`, host tensor creation and tiny D2D copies inside graph replay loops. |
| 2026-05-19 | #1433/#1551 | chunked prefill | Added Qwen3.5 chunked prefill and NPU fused infer attention support. | MTP validate can be represented as chunked-prefill-like input; verify graph/attention branch carefully. |
| 2026-05-21 | #1492/#1597 | MTP shape | Fixed Qwen3.5/3.6 MTP verify shape mismatch for larger `num_speculative_tokens`. | Test `num_speculative_tokens` > 1, not only nst=1. |
| 2026-05-24 | #1537 | precision rollback | Reverted Qwen3.5 TileLang GDN precision regressions. | Do not keep kernel wins without dataset-slice precision evidence. |
| 2026-05-24 | #1538 | graph model type | Fixed Qwen3.5 model type checks in ACL graph. | Model-type predicates must include text/MoE aliases and future Qwen3.5-prefixed types. |
| 2026-05-26 | #1496/#1422 | linear state capacity | Used max concurrent requests for single-block and linear-state allocation. | Capacity fixes must account for VLM and non-VLM branches when rebasing. |
| 2026-05-28 | #1529/#1585 | conv tiling | Fixed causal_conv1d tiling failure for padded/concurrent Qwen3.5 GDN decode. | Reproduce with concurrent decode and padded batch, not single request only. |
| 2026-05-28 | #1567 | weight transforms | Serialized Qwen3 Next attention weight transforms. | Avoid races and repeated mutation when multiple workers/ranks initialize. |
| 2026-05-29 | #1536 | MTP conv reuse | Reused causal_conv1d for Qwen3.5 MTP verify on NPU. | Later reverted for precision risk; treat this as a cautionary optimization, not a safe baseline. |
| 2026-05-29 | #1548/#1414 | chat stop | Added Qwen3.5 chat stop token. | Accuracy smoke should use correct tokenizer/chat template/stop tokens. |
| 2026-05-29 | #1556 | PD disagg | Added Qwen3.5 PD disaggregation with llmdatadist on NPU. | Validate KV transfer, layer synchronization and speculative worker paths. |
| 2026-06-01 | #1571 then #1628 | GDN TileLang | Added then reverted corrected `chunk_gated_delta_rule_fwd_h` due to regression. | Keep explicit rollback notes; precision must override local kernel speed. |
| 2026-06-01 | #1610 | schedule overlap | Fixed crash when MTP and schedule overlap are enabled on Qwen3.5. | Include schedule-overlap in MTP smoke matrix. |
| 2026-06-01 | #1614 then #1629 | MTP conv params | Padded MTP conv host params for concurrent graph, then reverted with MTP conv reuse due to precision issues. | Host-param padding and conv reuse need separate validation; do not bundle risky optimizations. |
| 2026-06-01 | #1623 | CP + MTP | Fixed CP+MTP KV-split double cache-slot remap. | Nested MTP/CP paths can remap cache slots twice; inspect `cp_partitioned` guards. |
| 2026-06-01 | local `4fa0cb6c` | validate attention | Fixed Qwen3.5 MTP validate attention path. | Verify `prepare_validate_inputs` and attention metadata agree on validate width. |
| 2026-06-02 | #1629 / `6655687b` | precision rollback | Reverted MTP causal_conv1d reuse and conv host-param padding due to precision issues. | Use as a red flag when optimizing MTP conv path again. |
| 2026-06-03 | #1638 / `b2050d3e` | conv params | Fixed conv1d operator parameter update causing Qwen3.5/Qwen3.6 accuracy degradation. | Graph replay must update all conv params that vary by step/request. |
| 2026-06-04 | #1635 / `d805eb4c` | graph inputs | Handled Qwen3.5 MTP graph inputs and decode input stabilization. | Guard decode-only persistent params; normalize MTP decode position/KV length only within speculative width. |
| 2026-06-04 | #1648 / `f3356069` | attention mask | Avoided dense Qwen3 Next hybrid attention masks on NPU. | Dense masks can add memory/host pressure; prefer metadata-driven NPU attention paths. |

## Case: Qwen3 Next Baseline Support

- related_prs: #989 (`d1354441`)
- touched_paths: `qwen3_next.h`, `qwen3_next_hybrid_base.h`,
  `qwen3_next_attention`, `qwen3_next_gated_delta_net`, KV cache and state dict utilities
- optimization_intent: make Qwen3 Next run on NPU with hybrid attention and linear-state support
- validation: commit history indicates broad model support; require local smoke/perf before using as a baseline
- risks: shared base changes flow into Qwen3.5; attention metadata, partial RoPE,
  linear state and graph capture are common failure points
- next_checks: when Qwen3.5 regresses, first compare the shared Qwen3 Next hybrid
  base and GDN base rather than only Qwen3.5 leaf files

## Case: Qwen3.5 Model and Checkpoint Support

- related_prs: #1094 (`0f95a430`)
- touched_paths: `qwen3_5.h`, `qwen3_5_gated_delta_net`,
  `qwen3_gated_delta_net_base`, `qwen3_next_hybrid_decoder_layer_base`
- optimization_intent: add Qwen3.5/Qwen3.5-MoE model family by reusing the
  Qwen3 Next hybrid architecture and specializing the GDN path
- validation: model loader and runtime support landed before later MTP/graph optimizations
- risks: Qwen3.5 is not isolated; shared GDN base and hybrid decoder base affect
  Qwen3 Next, Qwen3.5, Qwen3.5-MoE and Qwen3.6-like paths
- next_checks: for precision regressions, check checkpoint mapping, model type
  aliases, GDN state order, conv state and chat stop token handling

## Case: Qwen3.5 / Qwen3 Next GDN Operator Evolution

- related_prs: #1262, #1291, #1307, #1322, #1345, #1357, #1529, #1585, #1638
- touched_paths: `qwen3_gated_delta_net_base`, `npu_recurrent_gated_delta_rule`,
  `chunk_gated_delta_rule`, `conv1d_update`, `conv1d_fn`, `npu_ops_api`
- optimization_intent: replace expensive or shape-fragile torch sequences with
  NPU fused operators for recurrent GDN, chunk GDN and causal convolution
- validation: single-op and end-to-end validation are both required; several
  later commits fixed tiling and parameter-update issues that only appear with
  padded or concurrent decode
- risks: conv host params, state indices, `g`/`beta` dimension order, dynamic
  batch padding and graph replay values are correctness-sensitive
- next_checks: when output is garbled or CEval drops, inspect whether every
  per-step conv/GDN parameter is refreshed before graph replay

## Case: TileLang and Fusion Rollbacks

- related_prs: #1315, #1329, #1330, #1537, #1571, #1628
- touched_paths: `split_qkv_rmsnorm_mrope`, TileLang wrappers,
  `chunk_gated_delta_rule_fwd_h`, `qwen3_next_attention`
- optimization_intent: fuse QKV split, RMSNorm, MRoPE and GDN chunk kernels to
  reduce memory movement and host/kernel overhead
- validation: PR history contains both successful integration and explicit
  rollbacks for precision regressions
- risks: fused kernels can pass small smoke tests but fail dataset slices; TP
  split specializations need runtime guards and fallback
- next_checks: before reviving a reverted kernel, run deterministic prompts,
  target dataset slices, full target tasks when known risky, and before/after profiling

## Case: Chunked Prefill and Token-Flat Prefill

- related_prs: #1350, #1454, #1433, #1551
- touched_paths: `attention_metadata_builder`, `attention`, `qwen3_gated_delta_net_base`,
  `acl_graph_executor_impl`
- optimization_intent: support token-flat prefill with correct recurrent state
  and enable Qwen3.5 chunked prefill on NPU
- validation: prefill shape tests are not enough; MTP validate reuses a
  chunked-prefill-like shape and must be checked separately
- risks: attention branch selection, recurrent state indexing and graph capture
  may disagree about whether the input is prefill, chunked prefill, decode or spec verify
- next_checks: when MTP validate fails, compare `q_max_seq_len`, `kv_seq_lens`,
  `new_cache_slots`, forward type and graph key construction

## Case: Qwen3.5 MTP Enablement and Export

- related_prs: #1119, #1409, #1574
- touched_paths: `qwen3_5_mtp.h`, `tools/export_mtp.py`,
  `embedding_cache`, `kv_cache_shape`, `attention_metadata`, `mtp_worker_impl`,
  `acl_graph_executor_impl`
- optimization_intent: support Qwen3.5/Qwen3.5-MoE draft models and target
  verification with exported MTP weights
- validation: MTP must be validated with exported MTP weights, explicit draft
  path, server-side speculative counters and deterministic accuracy checks
- risks: running without real `--draft_model` or without exported MTP weights can
  produce misleading client-side acceptance-rate numbers
- next_checks: confirm `draft_model`, `draft_devices`, `num_speculative_tokens`,
  exported config/model type, `num_nextn_predict_layers`, and server counters

## Case: Qwen3.5 MTP Graph Stability

- related_prs: #1538, #1597, #1610, #1614, #1623, #1629, #1635, #1638
- touched_paths: `mtp_worker_impl`, `acl_graph_executor_impl`,
  `acl_graph_persistent_param`, `worker_service`, `qwen3_gated_delta_net_base`
- optimization_intent: make MTP verify graph inputs, validate width, conv params,
  position/KV length and schedule-overlap paths stable
- validation: repeated one-request smoke, fixed prompt set, dataset-slice
  accuracy and warmup performance are all needed for Qwen3.5 MTP graph changes
- risks: decode-only graph persistent params cannot blindly apply to spec verify;
  conv host-param padding and causal_conv1d reuse were reverted due to precision issues
- next_checks: if `PagedAttentionOperation setup failed`, `position/kv_len mismatch`,
  or garbled MTP output appears, inspect validate input construction before optimizing performance

## Case: MTPWorkerImpl::run_validate Verify Path

- related_prs: #1409, #1574, #1597, #1635
- touched_paths: `MTPWorkerImpl::run_validate`,
  `MTPWorkerImpl::prepare_validate_inputs`, `attention_metadata_builder`,
  `acl_graph_executor_impl`
- optimization_intent: build target-model verification inputs for
  `num_speculative_tokens + 1` tokens and run the Qwen3.5 verify attention path
- validation: compare deterministic MTP output, server-side accepted/draft
  counters, and graph/non-graph behavior on the same fixed prompts
- risks: validate width, `q_max_seq_len`, `kv_seq_lens`, `new_cache_slots` and
  accepted-token rollback must describe the same speculative step
- next_checks: if path filtering points here, inspect validate input shape before
  changing GDN kernels or sampling code

## Case: Qwen3.5 VLM and PD Disaggregation

- related_prs: #1540, #1556
- touched_paths: `vlm_engine`, `qwen3_5` VLM model, `mposition`,
  `kv_cache_transfer`, `speculative_engine`, PD scheduler/worker paths
- optimization_intent: support Qwen3.5 image/video inputs and PD disaggregation
  with NPU KV transfer
- validation: text-only smoke is insufficient when rebasing these changes; run
  VLM loader tests or request smoke if VLM code is touched
- risks: branches that fix MTP may accidentally drop VLM changes during rebase;
  PD paths add remote worker and transfer ordering constraints
- next_checks: for PR rebases, explicitly compare VLM files and PD transfer files
  against the source PR before declaring conflict resolution complete

## Case: Qwen3 Next / Qwen3.5 Weight Transform and Mask Risks

- related_prs: #1400, #1567, #1648
- touched_paths: `qwen3_next_attention`, `qwen3_next_hybrid_base`
- optimization_intent: make weight transforms idempotent/serialized and avoid
  dense attention masks on NPU
- validation: run at least fixed-prompt accuracy and compare startup/init logs
  when changing weight transform code
- risks: repeated or concurrent weight adjustment can introduce precision
  regressions; dense masks can create memory pressure and host overhead
- next_checks: check for in-place weight mutation, one-time guards, mutex/serialization,
  and metadata-driven attention mask paths

## Case: nst=1 Was Better Than nst=2

Initial expectation: `num_speculative_tokens=2` should improve throughput by reducing
the number of decode iterations.

Observed result: nst=2 regressed TTFT and TPOT on long-input workloads. nst=1 was the
better balance on the validated A3 setup because draft prefill, verify cost, and
DeltaNet state reserve dominated the extra speculative-token benefit.

Validation lesson:

- Compare the same code version and same workload.
- Always use warmup for formal perf results.
- Report TTFT, TPOT, TPS and acceptance counters together.
- Treat nst>1 as a new configuration that needs fresh accuracy and profiling evidence.

## Case: MTP Transpose Elimination

Intent: remove repeated transpose work in Qwen3.5 MTP verify convolution.

Change pattern:

- Cache the transposed convolution weight once instead of transposing every step.
- Keep the MTP verify path in the expected layout so round-trip transpose kernels disappear.
- Put the logic in the small operator/model-path code rather than broad scheduler code.

Evidence pattern:

- Precision: validate a deterministic small set before performance claims.
- Profiling: compare transpose kernel call count and device time before/after.
- Performance: compare baseline/current with the same warmup and workload.

Representative validated result from an A3/Qwen3.5-27B run:

| Metric | Before | After | Delta |
|---|---:|---:|---:|
| dominant transpose variant | 14,400 calls / 207.8 ms | 960 calls / 17.3 ms | -93.3% calls |
| all transpose-like kernels | 14,690 calls / 211.9 ms | 1,210 calls / 21.1 ms | -190.8 ms |
| output throughput | 36.11 tok/s | 39.54 tok/s | +9.5% |
| TPOT | 24.2 ms | 21.9 ms | -9.5% |
| speculative accept rate | 47.7% | 47.7% | unchanged |

Reusable reference: `skills/xllm-npu-sota-loop/references/mtp-transpose-elimination-case.md`.

Risk:

- Layout fixes can silently change semantics. Do not accept a pure performance win without
  a small deterministic accuracy check and at least one dataset slice.

## Case: MTP Graph/Chunked Prefill Fix

Symptom examples:

- `PagedAttentionOperation setup failed`
- `decode context position/kv_len mismatch`
- `ACL graph persistent param only supports decode`
- MTP output becomes garbled while non-MTP output is normal.

Root-cause pattern:

- Qwen3.5 MTP validate can enter a different forward type from ordinary decode.
- Decode-only graph persistent parameter logic must not be applied to non-decode batches.
- Chunked-prefill decisions in speculative verify must match the path expected by the
  ATB/spec-kernel or Qwen3.5 verify implementation.
- Position/KV length checks are sensitive to accepted-token rollback and cache update order.

How to localize:

1. Reproduce with one deterministic chat request before using a full benchmark.
2. Run A/B: no MTP, MTP with graph off, MTP with graph on.
3. Compare against the known-good preview branch for MTP-specific code paths.
4. Inspect whether the failing stack enters `run_validate`, graph capture, or
   `update_decode_step_input`.
5. After each fix, run repeated single-request smoke, then dataset-slice accuracy, then perf.

Expected fix shape:

- Preserve the original ATB spec-kernel path while explicitly allowing the Qwen3.5 verify path.
- Guard decode-only persistent graph parameter updates by forward type.
- Keep accepted-token/KV bookkeeping aligned between target and draft contexts.

## Case: Acceptance Rate Measurement Pitfall

Do not conclude MTP is enabled or healthy only from a client-side acceptance-rate field.
Client tools can infer acceptance from output/request shapes, and that may not match the
server-side speculative path.

For speculative decoding, capture these xLLM counters before and after a fixed prompt set:

| Counter | Meaning |
|---|---|
| `speculative_num_accepted_tokens_total` | tokens accepted from draft |
| `speculative_num_draft_tokens_total` | draft tokens proposed |

Use:

```text
true_accept_rate = accepted_delta / draft_delta
```

If client-side and server-side rates disagree, trust the server counters for MTP health.

## Case: Sampling Postprocess Top-P/Top-K

Observed optimization space:

- top_p/top_k postprocess can add host synchronization and small tensor copy overhead.
- Removing sampling from the workload changes the problem definition, so compare both
  deterministic and sampling-enabled scenarios separately.
- When the business scenario uses `temperature=0`, sampling-postprocess optimization may
  be low priority even if profiling shows a local hotspot.

Validation lesson:

- Use deterministic requests to protect accuracy when touching sampling code.
- For performance, keep sampling parameters identical between baseline/current.
- Do not mix profiling run timing with formal non-profiling evalscope timing.

## Regression Checklist

- [ ] `git status --short` is clean before build and before push.
- [ ] Submodules are updated before local CI.
- [ ] `python setup.py build test --device npu` passes for xLLM PR changes.
- [ ] Single deterministic prompt is readable.
- [ ] Fixed small prompt set has no new malformed output.
- [ ] Dataset slice or target task is run when a previous bug was data-dependent.
- [ ] Perf run uses warmup.
- [ ] MTP run records server-side speculative counters.
- [ ] Profiling run has a separate artifact directory and is not used as formal perf timing.
