# Triton-Ascend 算子模式

## 定位

Triton-Ascend 路径适合快速实现中等复杂度的向量化/块化 kernel，用于填补
PyTorch/torch_npu 融合算子不足和 AscendC 开发成本较高之间的空档。

优先使用场景：

- 热点是 elementwise、mask、gather/scatter、small reduction、sampling 后处理。
- 需要比 PyTorch eager 少 kernel launch / 少中间 tensor / 少 host sync。
- TileLang 表达或构建成本不合适，AscendC 又过重。
- 已有 `third_party/torch_npu_ops/triton_npu` 运行时和样例可复用。

不优先使用场景：

- 需要深度利用 Cube MatMul、复杂 DMA pipeline 或手写通信。
- shape 极不稳定，缺少明确 specialization 策略。
- 构建环境缺少 Triton-Ascend runtime 或二进制资产。

## Kernel Skeleton

```python
import torch
import triton
import triton.language as tl


@triton.jit
def vec_add_kernel(x, y, out, n: tl.constexpr, block: tl.constexpr):
    pid = tl.program_id(0)
    offsets = pid * block + tl.arange(0, block)
    mask = offsets < n
    xv = tl.load(x + offsets, mask=mask, other=0.0)
    yv = tl.load(y + offsets, mask=mask, other=0.0)
    tl.store(out + offsets, xv + yv, mask=mask)


def vec_add(x, y):
    out = torch.empty_like(x)
    n = x.numel()
    block = 1024
    grid = (triton.cdiv(n, block),)
    vec_add_kernel[grid](x, y, out, n, block)
    return out
```

## 设计规则

- 用 `tl.constexpr` 固定会影响编译和 tiling 的参数。
- 对 decode 小 shape 单独 specialization，避免为长 prefill shape 牺牲 TPOT。
- mask 必须覆盖尾块，不能依赖输入刚好对齐。
- 避免在 Python wrapper 中做会触发同步的 `.item()`、CPU copy 或 shape 数据回读。
- kernel 参数只传 device tensor、标量和 constexpr；不要传请求私有的 host 状态。

## 适合优先尝试的 xLLM 路径

- sampling 后处理：top_k/top_p mask、accepted mask、small prefix logic。
- MTP verify 辅助：小 tensor copy/fill/mask 融合。
- decode metadata 辅助：可纯 device 化的小规模 shape/position 更新。

## 验证门禁

- 与 PyTorch reference 比较输出和 mask。
- 覆盖 `batch=1`、小 batch、多 batch、非整除 block 的尾块。
- 正式性能用 warmed-up evalscope；profiling 用于证明 kernel launch 或 host sync 减少。
- 若 Triton-Ascend 编译/运行依赖本地二进制资产，先记录环境门禁，不把缺资产误判为代码错误。
