# TileLang DSL 常用模式

## 概述

TileLang 是由上海交大 IPADS 研究所开发的 NPU 算子 DSL，专为华为昇腾设计。xLLM 使用 TileLang-Ascend 版本。

入口文件：`xllm/compiler/tilelang/`

## 基本结构

```python
import tilelang.language as T

@T.prim_func
def my_kernel(
    A: T.Tensor([M, K], dtype="float16"),
    B: T.Tensor([K, N], dtype="float16"),
    C: T.Tensor([M, N], dtype="float16"),
):
    # Tiling 声明
    with T.grid(M, N) as (m, n):
        with T.block("compute"):
            # 局部 buffer
            with T.tile_scope(
                tile_M=64, tile_N=64, tile_K=32,
                block_M=2, block_N=2, block_K=1
            ):
                # Data copy (MTE2)
                T.copy(A_tile, A_shared)
                T.copy(B_tile, B_shared)
                # Compute (AICore)
                T.matmul(A_shared, B_shared, C_tile, accumulate=True)
```

## MatMul Tiling 策略

### A2/A3 初始配置

```python
# 先通过 PlatformAscendC / profiling 查询 UB、L1、L0 和 core 数；
# 下列 tile 只是启动搜索的初始候选，不是跨 A2/A3 通用常量。
# 双 buffer 估算:
# 2*(tile_M*K + K*tile_N)*dtype_bytes + tile_M*tile_N*dtype_bytes
# 必须小于查询得到的 local memory budget。

# 小 batch (decode)
tile_M, tile_N, tile_K = 16, 128, 64

# 中 batch (prefill normal)
tile_M, tile_N, tile_K = 64, 128, 64

# 大 batch (prefill long seq)
tile_M, tile_N, tile_K = 128, 128, 64
```

### Tile size 计算

```python
def ub_usage(tile_M, tile_N, tile_K, dtype_bytes=2):
    # 双 buffer: 2x input buffers
    a_size = tile_M * tile_K * dtype_bytes * 2
    b_size = tile_K * tile_N * dtype_bytes * 2
    # 单 buffer: output
    c_size = tile_M * tile_N * dtype_bytes
    return a_size + b_size + c_size

# ub_budget_bytes 必须来自 GetCoreMemSize(CoreMemType::UB) 或运行时 profile。
assert ub_usage(64, 128, 64) <= ub_budget_bytes
```

## Softmax Pattern

```python
@T.prim_func
def softmax_kernel(X: T.Tensor([M, N], "float16"), Y: T.Tensor([M, N], "float16")):
    # Row max reduction (fp32 accumulator for stability)
    row_max = T.alloc("float32", [M])
    with T.grid(M) as m:
        with T.tile_scope(tile_M=1, tile_N=64):
            T.reduce_max(X[m, :], row_max[m], axis=1)
    
    # Shift + Exp
    with T.grid(M, N) as (m, n):
        with T.tile_scope(tile_M=1, tile_N=64):
            shifted = X[m, n] - row_max[m]
            exp_val = T.exp(T.cast(shifted, "float32"))
            T.copy(exp_val, temp[m, n])
    
    # Row sum
    row_sum = T.alloc("float32", [M])
    with T.grid(M) as m:
        with T.tile_scope(tile_M=1, tile_N=64):
            T.reduce_sum(temp[m, :], row_sum[m], axis=1)
    
    # Normalize
    with T.grid(M, N) as (m, n):
        with T.tile_scope(tile_M=1, tile_N=64):
            Y[m, n] = T.cast(temp[m, n] / row_sum[m], "float16")
```

## RMSNorm Pattern

```python
@T.prim_func
def rmsnorm_kernel(
    X: T.Tensor([M, N], "float16"),
    gamma: T.Tensor([N], "float16"),
    Y: T.Tensor([M, N], "float16"),
    eps: T.float32 = 1e-6,
):
    with T.grid(M) as m:
        # Compute variance in fp32
        with T.tile_scope(tile_M=1, tile_N=N):
            x_fp32 = T.cast(X[m, :], "float32")
            var = T.mean(x_fp32 * x_fp32)
            inv_rms = T.rsqrt(var + eps)
            # Normalize and scale
            normed = x_fp32 * inv_rms
            gamma_fp32 = T.cast(gamma, "float32")
            Y[m, :] = T.cast(normed * gamma_fp32, "float16")
```

## RoPE Pattern

```python
@T.prim_func
def rope_kernel(
    Q: T.Tensor([B, S, H, D], "float16"),
    cos: T.Tensor([S, D], "float16"),
    sin: T.Tensor([S, D], "float16"),
    Q_out: T.Tensor([B, S, H, D], "float16"),
    head_dim: T.int32,
):
    with T.grid(B, S, H) as (b, s, h):
        with T.tile_scope(tile_D=head_dim // 2):
            q_even = T.cast(Q[b, s, h, 0::2], "float32")
            q_odd = T.cast(Q[b, s, h, 1::2], "float32")
            c = T.cast(cos[s, 0::2], "float32")
            s_val = T.cast(sin[s, 0::2], "float32")
            
            q_rot_even = q_even * c - q_odd * s_val
            q_rot_odd = q_odd * c + q_even * s_val
            
            # Interleave back
            Q_out[b, s, h, 0::2] = T.cast(q_rot_even, "float16")
            Q_out[b, s, h, 1::2] = T.cast(q_rot_odd, "float16")
```

## xLLM 中使用方式

```bash
# 编译 + 运行 TileLang kernel
TL_ROOT=$PWD/third_party/tilelang-ascend \
python xllm/compiler/tilelang_launcher.py \
    --op my_kernel \
    --shape "M=128,K=4096,N=8192"

# xLLM 会自动查找 xllm/compiler/tilelang/ 下的实现
```

## 调试技巧

### 打印中间值（仅 eager 模式）

```python
# TileLang 不支持 print，但可以用 debug dump
T.debug_dump(buffer, "output.bin")
```

### 性能分析

```python
# 启用 tilelang profiler
TILELANG_PROFILING=1 python xllm/compiler/tilelang_launcher.py ...
```

### 常见错误

| 错误 | 原因 | 解决 |
|------|------|------|
| UB overflow | tile 过大 | 减小 tile_M/tile_N/tile_K |
| Shape mismatch | shape 不兼容 tile | 确保 dim 是 tile_size 的倍数 |
| Compile timeout | 复杂 kernel | 拆分 kernel 或简化控制流 |
