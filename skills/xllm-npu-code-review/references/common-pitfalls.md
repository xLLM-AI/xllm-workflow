# NPU 常见陷阱

## 1. KV Cache 格式不一致

**症状**：Precision 错误、输出 NaN

**原因**：Prefill 和 Decode 使用不同的 KV Cache 格式（NZ vs ND）

**检查**：
```cpp
// 确认两处都使用 NZ 格式
auto kv_dtype = get_kv_cache_dtype();
// Prefill
write_kv_cache(block_table, slot_mapping, key_nz, value_nz);
// Decode  
read_kv_cache(block_table, slot_mapping, key_nz, value_nz);
```

---

## 2. Graph Break

**症状**：图编译失败、AICore 利用率突然降低

**常见原因**：

| 原因 | 解决方案 |
|------|---------|
| 动态 shape（shape 未参数化） | 固定 shape 或使用动态 shape 分桶 |
| 不支持的算子 | 实现 GE 对应的 op，或 fallback 到 eager |
| Python data-dependent 控制流 | 将条件逻辑下沉到 C++/AscendC |
| AICPU 算子 | 将 AICPU 算子迁移到 AICore |

---

## 3. UB 溢出

**症状**：编译失败或运行时报 "Out of L1 memory"

**原因**：TileLang/AscendC kernel 的 UB 分配超过 2MB（A3 限制）

**检查**：
```python
# A3: UB per AICore = 2MB
ub_budget = 2 * 1024 * 1024  # bytes
tile_size = block_M * block_K * 2  # fp16 = 2 bytes
if tile_size * 2 > ub_budget:
    # reduce block_M or block_K
```

---

## 4. 通信未等待

**症状**：精度错误、偶尔 NaN

**原因**：AllReduce/AllGather 完成前使用了结果

```cpp
// DON'T:
hccl_all_reduce(tensor, group);
auto result = tensor;  // 通信可能未完成！

// DO:
hccl_all_reduce(tensor, group);
rtStreamSynchronize(stream);  // 或确保在同一 stream
auto result = tensor;
```

---

## 5. MTE3/AICore 资源竞争

**症状**：性能退化、AICore 利用率低于预期

**原因**：多个 kernel 同时竞争 MTE3 带宽

**检查**：查看 profiling 中 MTE3 的利用率，如果接近 100% 考虑减少数据搬运量。

---

## 6. NPU 内存碎片

**症状**：显存使用率低但分配失败

**原因**：xTensor 内存池碎片化

**解决**：
```bash
# 调整初始内存分配
xllm serve ... --gpu-memory-utilization 0.95
# 或启用碎片整理
xllm serve ... --enable-defrag
```

---

## 7. 混合精度溢出

**症状**：输出有 Inf/NaN

**常见场景**：
- FP16 累加导致溢出
- Softmax 在 FP16 下数值不稳定
- Attention score 计算溢出

**解决**：
```cpp
// Softmax: 使用 FP32 中间计算
float max_val = rowmax(input);
float* shifted = input - max_val;  // 数值稳定
float* exp_val = exp(shifted);
float sum = reduce_sum(exp_val);
output = exp_val / sum;
```

---

## 8. 多进程冲突（TP > 1）

**症状**：启动失败、段错误

**原因**：多个 worker 进程同时访问同一 NPU 设备

```bash
# DO: 设置 ASCEND_RT_VISIBLE_DEVICES
# 每个 worker 应该看到完整的 NPU 列表，由框架内部分配

# DON'T: 在子进程中重新设置 visible devices
# xLLM 内部已经通过 worker rank 分配 NPU
```

---

## 9. GE 编译超时

**症状**：首次运行时长时间卡在编译阶段

**原因**：图编译首次运行需要编译所有 shape 的 subgraph

**解决**：
- 使用 warmup 提前编译
- 缓存 GE 编译结果
- 减少动态 shape 的分桶数量

---

## 10. 精度对不齐（xLLM vs GPU）

**症状**：与 GPU 版本的输出差异较大

**检查清单**：
1. 权重加载精度（量化误差）
2. KV Cache 精度（NZ 格式转换误差）
3. Attention 实现差异（FlashAttention vs 标准注意力）
4. 随机种子是否正确对齐
5. 检查 RMSNorm/LayerNorm 的 epsilon 值
