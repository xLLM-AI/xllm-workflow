# Big-Rock Optimization Gate

Use this gate before selecting implementation work in a long-running goal. It
keeps the loop focused on the largest remaining source of end-to-end loss.

## Loss Budget

Build a coarse but complete **exclusive critical-path wall-time budget** for one
named phase and workload before zooming into details:

| category | measured cost | share | confidence | evidence |
|---|---:|---:|---|---|
| model compute / main operators | | | | |
| communication | | | | |
| host scheduling and dispatch | | | | |
| graph gaps and synchronization | | | | |
| copies and memory movement | | | | |
| sampling and postprocess | | | | |
| unclassified | | | | |

Do not rank ideas while a large `unclassified` bucket could change the order.
The exclusive rows plus `unclassified` must sum to phase wall time within 5%.
Do not add asynchronous device busy time to host wall time. Record overlap or
hidden-time opportunity separately; it is evidence for removable fraction, not
another additive budget row.

## End-To-End Ranking

For each candidate estimate a range:

```text
gain_upper_bound = affected_budget * removable_fraction
priority_score = expected_gain / (implementation_cost * validation_risk)
```

Keep the measurement noise and remaining target gap beside every estimate.

## Optimization Levels

Inspect candidates from largest scope to smallest scope:

1. **L0 architecture/algorithm**: MTP policy, batching, parallelism,
   graph/eager boundary, model path, major fusion strategy.
2. **L1 pipeline/stage**: scheduling, communication overlap, rank skew,
   host/device overlap, repeated synchronization.
3. **L2 layer/operator**: dominant layer families, repeated operators, layouts
   and dispatch choices.
4. **L3 kernel/detail**: one launch, memcpy, scalar gap, tiling or instruction
   detail.

L3 is locked until L0-L2 are quantified and selected, rejected with evidence,
already implemented, or outside scope. A kernel bypasses this lock only when it
is itself a dominant budget item with the largest end-to-end upper bound.

## Selection Gate

The selected hypothesis must:

- address the largest actionable budget item, or explain why larger items are
  blocked;
- exceed the noise floor and close a meaningful part of the remaining gap;
- have no cheaper L0/L1 route to the same result;
- have a falsifiable measurement and rollback plan.

Default threshold: expected gain should close at least 20% of the remaining
target gap. If no candidate meets it, switch the goal to discovery instead of
accumulating micro-patches.

The gate has four executable outcomes:

- `PASS`: one candidate meets the gate and may enter implementation.
- `DISCOVERY`: attribution is insufficient; allow at most two bounded evidence
  rounds, each with one named next measurement.
- `BLOCKED`: larger candidates are outside scope or require an external change;
  stop the goal and record the blocker.
- `EXEMPT`: a sub-20% or L3 candidate is allowed only with an explicit reason,
  complete L0-L2 disposition, and one selected candidate.

Run `xllm-flow gate check --run-root <run>` before changing checkpoint phase to
`implementation`, `code`, or `patch`.

## Detail-Trap Signals

Return to the loss budget when:

- analysis focuses on microseconds while the target gap is milliseconds;
- two consecutive candidates improve less than the noise floor;
- ranking follows ease of implementation instead of end-to-end gain;
- one kernel is examined before stage-level attribution is complete;
- several small patches together cannot close 20% of the remaining gap.

After every accepted win, rebuild the budget and candidate ranking.

A cross-module hypothesis must still describe one causal mechanism, have one
joint A/B switch or rollback boundary, and avoid bundling independently useful
changes. Split implementation into stages when those conditions cannot hold.
