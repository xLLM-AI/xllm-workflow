# Profiling Artifact Schema

Profiling runs explain bottlenecks; they are not steady-state performance
measurements. Keep capture, workload, analysis, and human timeline notes
together.

Recommended directory:

```text
profiling/<run_id>/
  manifest.md
  capture.log
  workload.log
  PROF_*/
  mindstudio_profiler_output/
  analysis.json
  five_tables.md
  timeline_notes.md
  optimization_candidates.md
```

Required capture notes:

- xLLM service was started normally before profiling.
- `PROFILING_MODE=dynamic` was exported before service startup.
- `msprof --dynamic=on --pid <xllm_parent_pid>` attached to the parent xLLM
  process, not a device worker PID from `npu-smi`.
- Warmup happened before the formal `start` marker.
- `PROF_*` and `mindstudio_profiler_output/` were generated successfully.

`timeline_notes.md` should capture the concrete interval being explained. For
decode host-bound analysis, record intervals such as:

```text
replaceToken end -> next GatherV2 start
  duration_us:
  observed host calls:
    - aclnnInplaceCopy/GetWorkspaceSize
    - CustomPagedAttentionOperation::Setup
    - small D2D copy
    - aclnnInplaceFillScalar
    - aclmdlRIExecuteAsync
    - StreamWaitEvent
  suspected root cause:
  candidate fix:
  validation plan:
```

Rules:

- Missing `PROF_*`, missing `mindstudio_profiler_output/`, failed workload, or
  warmup mixed into the formal capture means `INCONCLUSIVE`.
- Prefill-focused and decode-focused traces should be collected separately when
  the optimization target is phase-specific.
- Always pair a profiling conclusion with a non-profiling before/after
  performance run before claiming user-visible speedup.
