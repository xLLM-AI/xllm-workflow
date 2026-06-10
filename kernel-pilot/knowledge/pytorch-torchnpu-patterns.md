# PyTorch / torch_npu 算子模式

## 定位

PyTorch / torch_npu 路径适合低风险验证、已有 NPU 融合算子替换和模型层局部
改写。它通常不是最终极致性能方案，但适合快速证明优化方向是否成立。

优先使用场景：

- 已有 `torch_npu.npu_*` 融合算子能直接覆盖热点路径。
- 优化目标是消除多余 layout/transpose/copy，而不是新增复杂 kernel。
- 需要先做精度稳定性验证，再决定是否进入 Triton-Ascend / TileLang / AscendC。
- 业务风险高，要求先保留 PyTorch eager 语义。

## 常见替换模式

### 1. 使用 torch_npu 融合算子

```python
# Before: 多个 eager op，可能产生中间 tensor 和同步
y = torch.nn.functional.layer_norm(x, normalized_shape, weight, bias, eps)

# After: 优先使用已验证的 NPU 融合接口
y = torch_npu.npu_layer_norm_eval(x, weight, bias, eps)[0]
```

要求：

- 先确认 dtype、shape、返回值语义和 PyTorch reference 一致。
- 对比 eager baseline 的最大误差、平均误差和端到端输出。
- 不要只看单算子变快；必须验证端到端 TPOT/TTFT/TPS。

### 2. 缓存 layout 转换结果

```python
class MyLayer(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.cached_weight_t = None

    def maybe_prepare_weight(self, weight):
        if self.cached_weight_t is None:
            self.cached_weight_t = weight.transpose(0, 1).contiguous()
        return self.cached_weight_t
```

要求：

- 只缓存不会随请求变化的权重或常量。
- 对 graph replay 中会变化的状态、position、cache index 不做 host 化缓存。
- 多卡/多线程路径要确认缓存生命周期和 device 一致。

### 3. 保持 shape contract 显式

```python
def run_kernel(x):
    # Document expected layout near the callsite.
    # x: [batch, seq, hidden], contiguous on NPU
    assert x.dim() == 3
    assert x.is_contiguous()
    return torch_npu.npu_some_op(x)
```

要求：

- 在调用点写清楚 `[B, T, C]`、`[T, B, C]`、`[B, H, T, D]` 等 layout。
- 如果为了性能跳过 transpose，必须有精度 A/B 和 profiling 证明。

## 验证门禁

- 单算子：reference 对齐，覆盖 observed shapes、边界 shape、dtype。
- 端到端：固定 prompt 小集或目标数据集 slice。
- 性能：正式 run 必须 warmup；profiling run 不作为正式性能结论。
- 回退：若收益来自减少同步或 copy，保留可快速回退的调用边界。
