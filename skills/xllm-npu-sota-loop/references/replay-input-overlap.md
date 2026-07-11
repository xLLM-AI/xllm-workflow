# Replay Input Prepare Overlap Pattern

Use this reference when profiling shows a decode-step host bubble before graph
replay, especially a boundary like:

```text
previous decode/postprocess event -> next MODEL_EXECUTE
```

The core idea is to move replay-input preparation out of the replay critical
path. Do not only make one copy faster if the device is waiting for a sequence
of host-side metadata updates.

## Applicability

This pattern is a good candidate when all are true:

- graph replay is enabled;
- schedule overlap or another reliable host-side overlap window exists;
- the workload is decode-heavy and shape/bucket-stable;
- profiling shows host work before graph replay, not slower device kernels;
- replay inputs or metadata can be prepared into stable buffers before replay.

It is usually a poor candidate when:

- graph capture requires model-specific metadata that cannot be prepared early;
- batch shape, DP state, speculative width, or KV layout changes every step;
- correctness depends on host views that may be mutated after prepare;
- the evidence points to a real kernel, communication, or memory-capacity bottleneck.

## Design Template

Use a narrow implementation loop:

```text
guard eligible decode path
-> choose inactive graph/persistent-param slot
-> prepare next replay inputs in overlap window
-> mark slot prepared
-> replay from prepared slot
-> do only minimal replay-time refresh
-> fallback to original update path when any guard fails
```

For xLLM NPU ACL graph code, the PR1668-style shape is:

```text
WorkerImpl:
  can_prepare_npu_graph_decode_input()
  can_skip_npu_graph_decode_sync()

AclGraphExecutorImpl:
  prepare_graph_input()
  graph_slots_[2]
  last_started_replay_slot_

AclGraph:
  prepare_replay_inputs()

GraphPersistentParam:
  update(..., skip_token_update=true)
  update_tokens(...)
```

The important architectural property is the ping-pong slot:

```text
step N:   replay slot A, prepare slot B
step N+1: replay slot B, prepare slot A
```

This preserves stable graph addresses while allowing the next step's metadata to
be staged before the next `graph_.replay()`.

## Guard Rules

Before enabling the fast path, check:

- graph mode is enabled;
- schedule overlap is enabled;
- backend is `llm`;
- batch is decode or an explicitly supported verify shape;
- model does not require graph-forward metadata that must be prepared at replay;
- DP metadata is complete and all participating ranks are in decode when using
  global decode buckets;
- KV length does not exceed model capacity;
- graph key exists in the inactive slot;
- fallback path is unchanged when any condition fails.

Do not rely on environment variables as the only safety mechanism. Env gates are
useful during exploration, but a mergeable PR should have code-level guards and
a documented rollback path.

## Validation

A valid before/after must include:

- warmed-up non-profiling benchmark for official TPOT/TTFT/TPS;
- profiling run only for diagnosis;
- pipeline artifact for the decode boundary, including `bubble-table.csv` and
  `analysis.json`;
- accuracy smoke if token IDs, sampling, graph metadata, or host views are
  touched;
- service logs proving the fast path was actually taken;
- dirty diff and exact commit SHA.

Suggested success evidence:

```text
host bubble median decreases
official warmed-up TPOT decreases above noise
kernel table does not explain the delta
no new sync/copy/event sequence appears in the median bubble
accuracy smoke passes
```

## Anti-Patterns

Avoid these failure modes:

- bundling unrelated micro-optimizations into the same PR;
- keeping known negative experiments behind env gates in a merge candidate;
- optimizing token copy while leaving metadata copy/fill on the critical path;
- replacing graph replay preparation with direct buffer writes without proving
  graph address, lifetime, and stream ordering invariants;
- treating a profiling run's performance number as the official benchmark.

## PR1668 Lesson

PR1668 is useful as a pattern because it stayed narrow:

- one primary hypothesis: replay-input preparation can be overlapped;
- localized runtime changes around worker/executor/graph persistent params;
- double-slot structure for stable captured addresses;
- conservative guards and fallback.

When future optimization work finds a similar host bubble, start with this
pattern before introducing custom kernels, async D2H rings, LmHead setup caches,
or broad runtime rewrites.
