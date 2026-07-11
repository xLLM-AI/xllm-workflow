# Qwen3 1.7B Optimization Dossier

## Metadata

| Field | Value |
|---|---|
| framework | xLLM |
| model_family | Qwen3 1.7B |
| scenario | NPU decode graph / schedule overlap / host bubble reduction |
| status | living dossier |

## Key Paths

| Path or Symbol | Why It Matters |
|---|---|
| `WorkerImpl::can_prepare_npu_graph_decode_input` | Guards whether schedule-overlap decode input preparation is legal. |
| `AclGraphExecutorImpl::prepare_graph_input` | Moves next graph replay input preparation into an overlap window. |
| `AclGraph::prepare_replay_inputs` | Prepares persistent replay tensors ahead of the next replay. |
| `GraphPersistentParam::update` | Updates graph persistent tensors; avoid replay-time full updates when already prepared. |
| `GraphPersistentParam::update_tokens` | Minimal replay-time token refresh when metadata has already been prepared. |
| `worker_impl.cpp` schedule-overlap path | Best place to trigger prepare after previous output and before next graph replay. |

## Case: PR1668 Replay-Input Prepare Overlap

- related_prs: PR #1668, local candidate `bench/qwen3-1p7b-pr1668`
- touched_paths: `xllm/core/runtime/worker_impl.cpp`,
  `xllm/core/runtime/acl_graph_executor_impl.cpp`,
  `xllm/core/runtime/acl_graph_executor_impl.h`,
  `xllm/core/runtime/acl_graph_persistent_param.cpp`,
  `xllm/core/runtime/acl_graph_persistent_param.h`,
  `xllm/core/framework/sampling/sampler.cpp`
- optimization_intent: reduce Qwen3 1.7B decode TPOT by moving ACL graph replay
  input and metadata preparation out of the immediate replay critical path.
- validation: local PR comparison task recorded PR1668 as the smaller and lower
  risk implementation versus PR1654; formal runtime performance still requires
  NPU gate, accuracy smoke, warmed-up perf, and profiling artifacts on the target
  machine before making a merge recommendation.
- risks: double-buffered graph slots must preserve stable graph addresses and
  not race with active replay; only enable for graph + schedule-overlap + LLM
  decode paths with clear fallback.
- next_checks: when profiling shows `previous decode output -> next MODEL_EXECUTE`
  host bubble, check whether graph replay inputs are still prepared immediately
  before replay. Prefer a double-slot prepare-overlap design over many unrelated
  env-gated micro-optimizations.

## Lessons

- Treat a decode host bubble as a critical-path problem, not only a total-work
  problem.
- First try to move replay input preparation into an existing overlap window.
- Use ping-pong graph slots or persistent-param slots when graph capture requires
  stable addresses.
- Keep the candidate narrow: guards, prepare API, replay fast path, fallback.
- Do not bundle independent experiments such as custom argmax, async D2H, LmHead
  setup cache, raw metadata copy, and service serialization changes unless each
  has separate A/B evidence and the final PR still needs all of them.
