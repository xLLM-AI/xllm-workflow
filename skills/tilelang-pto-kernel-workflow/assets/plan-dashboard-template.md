# Plan Dashboard — <op>

> 唯一状态真相源。状态只能是：待实现 / 通过 / 淘汰。

## 场景

- 创建时间：<created_at>
- Baseline：
- round0：
- 当前通过 baseline：
- 当前 round：

## Loop 控制

- 当前 Plan：
- 当前 step：SELECT
- 本轮唯一主要变量：
- 最后 Gate 与 verdict：
- 下一动作：
- 回退或派生目标：

## 主瓶颈

- Bound：
- Profile 证据：
- 热点源码 / generated source：
- 仲裁首推：

## Plans

> `plan_id` 必须使用 `plan-<id>`，对应文件必须是 `plans/plan-<id>.md`；表中每个数据行都会被校验。

| plan_id | 层次 | 来源 | 唯一主要改动 | 互斥组 | 可叠加 | 状态 | round | 证据摘要 | 决策原因 | 文件 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |

## 当前采纳

| plan_id | 改动 | enable / rollback | 性能 | 精度 | 文件 |
| --- | --- | --- | --- | --- | --- |

## Round 索引

| round | plan_id | 主要变量 | 完成 step | 是否复采 | perf/source/precision 路径 | verdict | next |
| --- | --- | --- | --- | --- | --- | --- | --- |

## 最终验收

- [ ] 无待实现 Plan
- [ ] 最终代码已与 round0 同口径复采
- [ ] 通过 Plan 均在最终路径
- [ ] 淘汰 Plan 已回退
- [ ] 可叠加组合已实测
- [ ] kernel / model / precision 分开报告
- [ ] rollback smoke 通过
