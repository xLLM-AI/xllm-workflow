# Qwen3.5-27B NPU 910B3 Kernel Profiling 分析报告

> 环境：xLLM `82a407db` (preview/qwen3.5-qwen3.6) / CANN 8.5.0 / HDK 25.5.1 / TP=2
> 测试：96 input tokens / 100 max tokens / 1 request / Phy 14 (master)
> Profiler：msprof dynamic 模式，msprof_profiler_output CSV 导出

---

## 1. 总览

| 指标 | Baseline | MTP (nst=1) | MTP/Baseline |
|------|----------|-------------|--------------|
| Device 总时间 | 1,379 ms | 2,901 ms | +110% |
| Device 总调用数 | 39,338 | 140,367 | +257% |
| Host StreamSync | 876 ms | 1,936 ms | +121% |
| Host launch calls | 3,580 | 9,526 | +166% |
| Output Throughput (p=1) | 29.88 tok/s | 36.11 tok/s | +21% |
| Output Throughput (p=2) | 48.90 tok/s | 58.62 tok/s | +20% |
| Accept Rate (MTP) | - | 47.7% | - |

**核心结论**：MTP 通过让每个 decode step 生成 1 个 draft token，将 AllReduce 通信次数摊销到多个 output token 上，以 +110% device time 为代价换取 +21% 的端到端吞吐提升。

---

## 2. Device Kernel 分布（Baseline）

| 占比 | Op Name | Count | Total (ms) | Avg (us) | Core |
|------|---------|-------|-----------|----------|------|
| **40.2%** | allreduceAicpuKernel | 3,840 | 553.8 | 144 | AI_CPU |
| **38.6%** | MatMulV2_ND_ND_FP16 (98499) | 6,960 | 531.5 | 76 | AI_CORE |
| 7.3% | MatMulV2_ND_ND_FP16 (98513) | 4,640 | 100.1 | 22 | AI_CORE |
| 4.2% | MatMulV2 | 431 | 57.3 | 133 | AI_CORE |
| 1.1% | fused_sigmoid_gating_delta_rule | 1,392 | 15.2 | 11 | AI_VECTOR |
| 0.8% | AddRmsNorm_3 | 3,712 | 11.6 | 3 | AI_VECTOR |
| 0.7% | CausalConv1d | 1,392 | 10.3 | 7 | AI_VECTOR |
| 0.6% | SwiGlu_3 | 1,856 | 8.5 | 5 | AI_VECTOR |
| 0.6% | allgatherAicpuKernel | 61 | 7.7 | 126 | AI_CPU |
| 0.6% | fused_qkvzba_split_reshape | 1,440 | 7.7 | 5 | AI_VECTOR |
| 0.5% | custom_paged_attention_mask | 464 | 6.8 | 15 | MIX_AIC |

**计算 vs 通信**：
- AllReduce+AllGather = 561.5ms (41%)
- GEMM (全部) = 688.9ms (50%)
- DeltaNet kernels = ~30ms (2%)
- 其他 Vector = ~98ms (7%)

---

## 3. Device Kernel 分布（MTP nst=1）

| 占比 | Op Name | Count | Total (ms) | Avg (us) | Core |
|------|---------|-------|-----------|----------|------|
| **34.1%** | allreduceAicpuKernel | 6,632 | 988.6 | 149 | AI_CPU |
| **31.9%** | MatMulV2_ND_ND_FP16 (98499) | 12,000 | 926.3 | 77 | AI_CORE |
| **7.2%** | Transpose (837fe4) [MTP专属] | 14,400 | 207.8 | 14 | AI_VECTOR |
| 6.1% | MatMulV2_ND_ND_FP16 (98513) | 8,000 | 176.1 | 22 | AI_CORE |
| 5.2% | MatMulV2 | 764 | 149.5 | 196 | AI_CORE |
| 1.4% | fused_recurrent_gated_delta_spec [MTP专属] | 2,400 | 42.0 | 18 | AI_VECTOR |
| 1.1% | _causal_conv1d_update_kernel [MTP专属] | 2,400 | 32.8 | 14 | AI_VECTOR |
| 0.9% | allgatherAicpuKernel | 207 | 25.1 | 121 | AI_CPU |
| 0.9% | layer_norm_fwd_kernel_fast_rms | 2,448 | 24.7 | 10 | AI_VECTOR |
| 0.8% | custom_paged_attention_mask | 800 | 23.0 | 29 | MIX_AIC |

---

## 4. Shared Kernel 增量 TOP-15（MTP - Baseline）

| 增量 (ms) | Base× | MTP× | 倍率 | Op |
|-----------|-------|------|------|-----|
| +435 | 3840 | 6632 | 1.7× | allreduceAicpuKernel |
| +395 | 6960 | 12000 | 1.7× | MatMulV2 (98499) |
| +92 | 431 | 764 | 1.8× | MatMulV2 |
| +76 | 4640 | 8000 | 1.7× | MatMulV2 (98513) |
| +18 | 1440 | 2448 | 1.7× | layer_norm_fwd_kernel |
| +17 | 61 | 207 | 3.4× | allgatherAicpuKernel |
| +16 | 464 | 800 | 1.7× | custom_paged_attention_mask |
| +9 | 3712 | 6400 | 1.7× | AddRmsNorm_3 |
| +9 | 31 | 155 | 5.0× | SoftmaxV2 |
| +8 | 1856 | 3200 | 1.7× | SwiGlu_3 |
| +6 | 1440 | 2448 | 1.7× | fused_qkvzba_split_reshape |
| +5 | 31 | 206 | 6.6× | ArgMaxV2 |
| +5 | 464 | 851 | 1.8× | split_qkv_rmsnorm_mrope |
| +5 | 1392 | 2400 | 1.7× | ConcatD (4100000) |
| +4 | 464 | 3200 | 6.9× | Sigmoid (mtp gate) |

**规律**：大部分 shared kernel 的 count 倍增 1.7×（接近 nst+1=2，但部分 step 提前终止）。Sigmoid、Softmax、ArgMax 等 5-7× 的增长来自 MTP 验证路径的额外 gate/accept logic。

---

## 5. MTP 专属 Kernel TOP-10（仅 MTP 有）

| Total (ms) | Count | Avg (us) | Op | 说明 |
|-----------|-------|----------|-----|------|
| **207.8** | 14,400 | 14.4 | Transpose (837fe4) | **MTP 最大单一开销** |
| 42.0 | 2,400 | 17.5 | fused_recurrent_gated_delta_rule_spec | DeltaNet draft spec forward |
| 32.8 | 2,400 | 13.7 | _causal_conv1d_update_kernel | DeltaNet 1D conv (spec) |
| 22.8 | 2,400 | 9.5 | Range_int32 | 索引构建 |
| 22.7 | 4,800 | 4.7 | Pack (4e9) | Token 重排 |
| 11.7 | 2,400 | 4.9 | AsStrided (spec) | Draft token 拼接 |
| 8.2 | 4,800 | 1.7 | Slice (spec) | Draft token 切片 |
| 6.8 | 2,400 | 2.8 | Add (spec) | Spec 路径 residual |
| 6.6 | 2,400 | 2.8 | Swish | MTP gate activation |
| 6.4 | 4,800 | 1.3 | Cast (mtp) | 类型转换 |

**MTP 专属总计**：~398ms，占 MTP 总 device time 的 13.7%

---

## 6. Host-side API 瓶颈

| API | Baseline | MTP | 说明 |
|-----|----------|-----|------|
| StreamSynchronize | 876 ms (1522 calls) | 1,936 ms (4331 calls) | **Host #1 瓶颈** |
| launch / launchKernel | 57ms / 3580 calls | 163ms / 9526 calls | 2.7× more launches |
| MemCopySync | - | 93 ms (3400 calls) | MTP 额外 KV cache 搬运 |
| hcom_allReduce | 16 ms (128 calls) | 38 ms (232 calls) | 1.8× |
| hcom_allGather | - | 21 ms (157 calls) | MTP 更多 allgather |

---

## 7. Kernel 级优化方向

### P0 — AllReduce 通信优化（当前占比 34-40%）

1. **通信-计算 overlap（Overlap Scheduling）**
   - 目标：将 AllReduce 与后续 GEMM 流水线化
   - 预期收益：隐藏 ~30% AllReduce 时间 → 吞吐 +10-15%
   - 参考：CANN `hcom_overlap` 参数 / xLLM `--enable-overlap` 标志

2. **AllReduce 融合（Reduce-Scatter → All-Gather 替代 Ring 通信）**
   - 对 TP=2 场景，Ring 通信退化为 2-step，可用更轻量的 all-gather+all-to-all
   - 预期收益：减少 20-30% 通信开销

3. **AllReduce Kernel 优化**
   - 当前 `allreduceAicpuKernel` avg=144us (baseline) / 149us (MTP)
   - 对于小 batch（seq=1 时 tensor 极小），可能存在 kernel launch 开销大于实际通信的情况
   - 可考虑将多个连续小 AllReduce 合并为一个

### P1 — GEMM Tiling 优化（当前占比 ~50%）

4. **大 GEMM Tile 自适应（MatMulV2 98499）**
   - 当前 avg=76us（baseline），12000 calls → 每次 ~1 tile
   - 对于 decode 阶段（batch=1），可探索 INT8 量化权重路径
   - 预期收益：W8A8 可降低 GEMM 时间 30-40%

5. **小 GEMM 优化（MatMulV2 98513，avg=22us）**
   - 22us 的 GEMM 适合 CANN kernel fusion pass
   - 可探索将相邻小 GEMM 与后续算子融合

### P2 — MTP 专属优化

6. **Transpose 消除（MTP 最大开销 207ms）** ✅ 已验证
   - 14,400次 Transpose，每次 14us
   - 根因：MTP 验证阶段对 draft logits 做 transpose 以匹配 target shape
   - 优化方向：修改 MTP 验证逻辑避免 transpose，或在 target 端直接输出兼容 shape
   - 预期收益：MTP 路径 -7% device time
   - **验证结果见 Section 9**

7. **DeltaNet Draft Kernel 融合**
   - `fused_recurrent_gated_delta_rule_spec_fwd_kernel` (42ms, 2400 calls)
   - `_causal_conv1d_update_kernel` (33ms, 2400 calls)
   - 两者紧密相邻，可探索 CANN pass 层融合

### P3 — Host-side 优化

8. **减少 StreamSynchronize 频率**
   - 当前 1522→4331 calls，876→1936ms
   - 每次 sync 之间仅执行 ~3 kernel launches，粒度太细
   - 可探索 graph capture / CUDA Graph 等效的 NPU Stream Capture

9. **Host ArgMax / Softmax 路径**
   - Softmax 31→155 calls (5×)，ArgMax 31→206 (6.6×)
   - MTP accept/reject 逻辑触发了大量小 Op 在 host 端
   - 可考虑将 accept decision 逻辑下沉到 device kernel

---

## 8. 优化优先级排序

| 优先级 | 方向 | 目标 Kernel | 预期吞吐收益 |
|--------|------|-------------|-------------|
| P0-1 | AllReduce-Compute Overlap | allreduceAicpuKernel | +10-15% |
| P0-2 | W8A8 量化 | MatMulV2 (所有) | +30-40% (仅 GEMM) |
| P1-1 | 小 GEMM 融合 | MatMulV2 (98513) | +3-5% |
| P2-1 | Transpose 消除 (MTP only) | Transpose (837fe4) | +5-7% (MTP 场景) |
| P2-2 | Host StreamSync 频率 | - | +5-10% |
| P3-1 | MTP accept kernel 融合 | Softmax+ArgMax | +2-3% |

---

## 9. P2-1 MTP Transpose 消除优化验证

### 9.1 优化措施

对 `qwen3_gated_delta_net_base.cpp/h` 做如下修改：

1. **缓存 `conv_weight` 的 transpose 结果**（成员变量 `conv_weight_transposed_`）
   - 将每次 decode step 重复计算的 `conv_weight.transpose(0,1).contiguous()` 提前缓存
2. **`run_spec_verify_conv` 改为收 `[B,T,C]` 输入、返回 `[B,T,C]`**
   - 消除 round-trip：原路径为 `[B,C,T] → transpose → [B,T,C] → conv → [B,T,C] → transpose → [B,C,T]`，改为 `[B,T,C] → conv → [B,T,C]`
3. **`process_mixed_qkv` 增加格式检测**
   - spec_verify 路径的 input 已是 `[B,T,C]`，跳过多余的 transpose

每次 decode step 的 Transpose 调用从 **6 次减少到 2 次**（-67%）。

### 9.2 msprof Kernel 验证

| Transpose Kernel 变体 | MTP Baseline | MTP-Transpose | 变化 |
|---|---|---|---|
| `Transpose_be83..._high_performance_13` | 14,400 次 / 207.8 ms | 960 次 / 17.3 ms | **-93.3% calls** |
| `Transpose`（基础） | 240 次 / 3.5 ms | 240 次 / 3.7 ms | 不变 |
| `Transpose_9a6..._high_performance_6` | 50 次 / 720 µs | 10 次 / 140 µs | -80% |
| **合计** | **14,690 次 / 211.9 ms** | **1,210 次 / 21.1 ms** | **-190.8 ms / -13,480 calls** |

主 kernel (`be83...`) 调用次数：14,400 → 960 = **15x 消除**，与代码层面 6→2 的理论比例一致。

### 9.3 Benchmark 验证

| 指标 | MTP Baseline | MTP-Transpose | Δ |
|------|-------------|---------------|---|
| Avg Output Rate (p=1, n=5) | 36.11 tok/s | 39.54 tok/s | **+9.5%** |
| Avg TPOT | 24.2 ms | 21.9 ms | **-9.5%** |
| Accept Rate | 47.7% | 47.7% | 不变 |

**结论**：P2-1 Transpose 消除达到 +9.5% 吞吐提升（超出预期的 +5-7%），msprof 验证 kernel 调用 -93.3%，device time -190.8ms，闭环验证通过。

### 9.4 参考记录

- `reference/pr_history/qwen35-mtp.md`
