# <plan_id> — <title>

## 假设

- 来源 / derived-from：
- 当前 Bound 与证据：
- 观察：
- 假设：
- 调优层次：TileLang / PTO / Production
- 本 Plan 唯一主要改动：
- 预期变化的 Profile 指标：
- 预期收益 / 风险 / 改动面 / 证据强度：
- 互斥组 / 可叠加：

## 验收

- 精度：
- source pattern：
- 资源：
- 性能：
- 跨 Shape：
- route / Graph：
- enable / rollback：

## Round Loop

> 每次重试或补证都新增全局 round，不覆盖旧记录。

| step | 输入 | 动作 | 必需证据 | Gate / verdict | next |
| --- | --- | --- | --- | --- | --- |
| R<N>.1 SELECT | 当前 baseline / Profile | 冻结唯一变量、验收线和 rollback | 选择与 why-not | READY / BLOCKED | IMPLEMENT 或补输入 |
| R<N>.2 IMPLEMENT | 已冻结 Plan | 单层次、单机制修改 | diff / source / object hash | BUILT / FAILED | VERIFY 或 DECIDE |
| R<N>.3 VERIFY | candidate | 精度、资源、Profile、A/B、Shape、route | artifact 路径与摘要 | PASS / FAIL / INCOMPLETE | REVIEW 或 DECIDE |
| R<N>.4 REVIEW | 本轮证据 | 独立核对因果、风险与噪声 | review 结论 | ACCEPT / REJECT / 补证 | DECIDE |
| R<N>.5 DECIDE | review | 通过、淘汰或待实现 | Dashboard 状态与回退 | CLOSED / NEXT_ROUND | 更新 baseline、回退或派生 |

## 实施记录

### round<N>

- commit / source hash / object hash：
- 修改文件：
- 编译：
- 精度自检：
- source audit：
- Profile / A/B：
- 遇到的问题：
- 当前 step / 下一跳：

## Review

### round<N>

- 路径命中：
- 机制证据：
- 精度：
- 资源与副作用：
- 性能：
- 是否需要复采：
- 建议：通过 / 淘汰 / 保持待实现

## 裁决与派生

- 最终状态：
- 证据摘要：
- 回退状态：
- 派生 Plan：
- 下一全局 round：
