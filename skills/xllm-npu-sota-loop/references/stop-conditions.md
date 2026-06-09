# 停止条件说明

## 1. xLLM 胜出

**条件**：在固定工作负载上，xLLM 的最佳配置结果击败 vLLM-Ascend 在相同 SLA 约束下的结果。

**验证方式**：
- 对比 summary.md 中的 xLLM best 与 vLLM-Ascend best
- xLLM 的 request throughput 严格大于 vLLM-Ascend
- 双方均满足 SLA 约束

**报告内容**：
- 最终性能数字
- xLLM winning-command
- 达成 SOTA 的优化历史（attempt-ledger）

---

## 2. 平局（1% 阈值内）

**条件**：xLLM 与 vLLM-Ascend 的吞吐差异在 1% 以内，且稳定在至少 3 个 benchmark 运行上。

**验证方式**：
```
|gap| = |xllm_throughput - vllm_throughput| / vllm_throughput * 100% <= 1%
```

**报告内容**：
- 当前数字 vs 初始数字（展示优化历史）
- 为什么认为已达到 SOTA

---

## 3. 硬件限制

**条件**：NPU 不支持某个关键特性，导致无法进一步缩小与 vLLM-Ascend 的差距。

**典型场景**：
- 某个关键算子无法在 A3 上编译（例如某些 Attention kernel shape 不支持）
- AICore 规格限制（SRAM 容量不足以支持某个优化）
- 缺少硬件级通信加速（相比目标框架的硬件配置）

**报告内容**：
- 明确记录哪个硬件限制阻止了进一步优化
- 建议的硬件升级方向

---

## 4. 瓶颈已达极限

**条件**：通过五表报告确认，热点路径已接近硬件或算法极限。

**判定依据**：
- AICore 利用率接近 100%（无空闲）
- 计算时间主要是 MatMul/GEMM，且其形状已是硬件最优
- 通信时间接近理论带宽（参考 hccl-test 结果）
- 没有可重叠的计算-通信窗口

**报告内容**：
- 当前瓶颈是什么
- 理论极限是多少
- 当前与极限的差距

---

## 5. 连续无进展

**条件**：连续 3 轮 evidence loop 迭代（每轮含新的优化方向）均未产生性能改善。

**验证方式**：
- 回顾 attempt-ledger.md 最近 3 条记录
- 如果全部是 "失败" 或 "无改善"，考虑停止

**报告内容**：
- 尝试了什么（3 条记录摘要）
- 为什么认为无法再优化
- 推荐的下一步方向
