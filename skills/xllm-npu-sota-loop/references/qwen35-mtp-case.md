# Qwen3.5 MTP SOTA Loop Case

This reference keeps one historical evidence-loop lesson out of the main
`xllm-npu-sota-loop` skill. Load it only when the current task needs a concrete
example of applying the loop to Qwen3.5 MTP optimization.

## Phase 0

| Parameter | Value |
|---|---|
| Model | Qwen3.5-27B |
| Precision | bf16 |
| NPU | 910B3/A3 |
| Parallelism | TP=2 in the initial case |
| CANN | 8.5.0 |
| Artifact root | `<run-root>/qwen35_27b_npu_sota` |

## Phase 1

Initial benchmark compared baseline, MTP, and an MTP transpose mitigation. The
MTP-transpose path improved throughput and TPOT enough to continue the loop.

| Config | Throughput Direction | TPOT Direction |
|---|---|---|
| Baseline | reference | reference |
| MTP | higher than baseline | lower than baseline |
| MTP-transpose | best in this case | best in this case |

## Phase 3

Profiling compared baseline / MTP / MTP-transpose traces. The key observation
was that communication and MatMul dominated overall time, while an MTP conv1d
shape/layout issue created an actionable local fix.

## Evidence Loop Round

```text
Research: profiling showed MTP conv1d shape/layout mismatch
Learn: model PR history showed strict v2 kernel weight-shape requirements
Code: use pre-transposed conv weight on the MTP path
Review: NPU code review checked graph/layout and precision risk
Validate: build, restart, benchmark, and accuracy smoke
Record: update attempt and optimization ledgers
```

## Failed Attempts

| Attempt | Direction | Result |
|---|---|---|
| chunked_prefill | scheduler | no improvement |
| memory | memory policy | no improvement |
| piecewise graph | graph strategy | no improvement |
| no_padding | padding elimination | no improvement |
| batch | batch strategy | no improvement |

Lesson: preserve failed experiments. They stop future agents from repeating
low-signal paths without new evidence.
