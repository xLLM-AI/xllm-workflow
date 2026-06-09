# AscendC C++ 常用模式

## 概述

AscendC 是华为昇腾官方的高性能算子开发语言，基于 C++ 扩展。适用于复杂控制流、自定义通信算子等 TileLang 难以表达的场景。

xLLM 中的 AscendC 算子位于 `third_party/kernel-coding/ascendc/`。

## 基本结构

```cpp
#include <acl/acl.h>
#include "kernel_operator.h"

extern "C" __global__ __launch_args__(...)
void my_kernel(GM_ADDR input, GM_ADDR output, int size) {
    // Get block index
    int32_t block_idx = GetBlockIdx();
    int32_t block_size = GetBlockNum();
    
    // 划分工作
    int32_t elements_per_block = size / block_size;
    int32_t offset = block_idx * elements_per_block;
    
    // 定义 local buffer
    __local__ half src[BUF_SIZE];
    __local__ half dst[BUF_SIZE];
    
    // 分块处理
    for (int i = 0; i < elements_per_block; i += BUF_SIZE) {
        // Copy GM → UB
        DataCopy(src, input + offset + i, BUF_SIZE);
        
        // Compute on UB
        Add(dst, src, scalar, BUF_SIZE);
        
        // Copy UB → GM
        DataCopy(output + offset + i, dst, BUF_SIZE);
    }
}
```

## Double Buffer 模式（核心优化）

利用 MTE2（UB↔L1）和 AICore 独立流水，实现数据搬运与计算重叠。

```cpp
constexpr int BUF_SIZE = 256;  // elements per tile, 128B aligned

__global__ void vec_mul_kernel(GM_ADDR x, GM_ADDR y, GM_ADDR z, int size) {
    int32_t block_idx = GetBlockIdx();
    int32_t total_tiles = (size + BUF_SIZE - 1) / BUF_SIZE;
    int32_t tiles_per_block = (total_tiles + GetBlockNum() - 1) / GetBlockNum();
    
    __local__ half x_buf[2][BUF_SIZE];  // Double buffer
    __local__ half y_buf[2][BUF_SIZE];
    __local__ half z_buf[BUF_SIZE];
    
    int cur_buf = 0;
    int next_buf = 1;
    
    // 初始化第一块
    int tile_idx = block_idx * tiles_per_block;
    DataCopy(x_buf[cur_buf], x + tile_idx * BUF_SIZE, BUF_SIZE);
    DataCopy(y_buf[cur_buf], y + tile_idx * BUF_SIZE, BUF_SIZE);
    
    for (int t = 1; t < tiles_per_block && (tile_idx + t) * BUF_SIZE < size; t++) {
        int next_offset = (tile_idx + t) * BUF_SIZE;
        
        // 异步加载下一块
        DataCopy(x_buf[next_buf], x + next_offset, BUF_SIZE);
        DataCopy(y_buf[next_buf], y + next_offset, BUF_SIZE);
        
        // 计算当前块
        Mul(z_buf, x_buf[cur_buf], y_buf[cur_buf], BUF_SIZE);
        
        // 写出当前块
        DataCopy(z + (tile_idx + t - 1) * BUF_SIZE, z_buf, BUF_SIZE);
        
        // Swap buffers
        std::swap(cur_buf, next_buf);
    }
    
    // 处理最后一块
    Mul(z_buf, x_buf[cur_buf], y_buf[cur_buf], BUF_SIZE);
    DataCopy(z + (tile_idx + tiles_per_block - 1) * BUF_SIZE, z_buf, BUF_SIZE);
}
```

## MatMul 优化模式

```cpp
// 使用 CUBE 单元（AI Core 内的 MatMul 加速器）
// 支持 shape: (M, K) x (K, N) → (M, N)
// fp16 Cube 指令通常以 16x16 cube 为基础；实际 tile 还要结合
// GetCoreMemSize 查询到的 L1/L0/UB 预算。

constexpr int TILE_M = 64;
constexpr int TILE_K = 32;
constexpr int TILE_N = 64;

__global__ void matmul_kernel(
    GM_ADDR A, GM_ADDR B, GM_ADDR C,
    int M, int K, int N
) {
    int block_idx = GetBlockIdx();
    int bm = block_idx / (N / TILE_N);
    int bn = block_idx % (N / TILE_N);
    
    __local__ half a_tile[TILE_M * TILE_K];
    __local__ half b_tile[TILE_K * TILE_N];
    __local__ float c_tile[TILE_M * TILE_N];  // fp32 accumulator
    
    Zero(c_tile, TILE_M * TILE_N);
    
    for (int k = 0; k < K; k += TILE_K) {
        // Load A tile
        DataCopy2D(a_tile, A + bm * TILE_M * K + k, K, TILE_K, TILE_M);
        // Load B tile
        DataCopy2D(b_tile, B + k * N + bn * TILE_N, N, TILE_N, TILE_K);
        
        // CUBE MatMul: c_tile += a_tile @ b_tile
        MatMul(c_tile, a_tile, b_tile, true);  // accumulate=true
    }
    
    // Write back (fp32 → fp16)
    __local__ half c_out[TILE_M * TILE_N];
    Cast(c_out, c_tile, RoundMode::ROUND_TOWARD_NEAREST, TILE_M * TILE_N);
    DataCopy2D(C + bm * TILE_M * N + bn * TILE_N, c_out, N, TILE_N, TILE_M);
}
```

## Reduce 模式

```cpp
// Warp-level reduction using shuffle (类似 CUDA warpReduceSum)
__device__ float warp_reduce_sum(float val) {
    for (int offset = 32; offset > 0; offset >>= 1) {
        val += WarpShuffleDown(val, offset);
    }
    return val;
}

// Block-level reduction
__device__ float block_reduce_sum(float val) {
    __shared__ float shared_mem[32];  // Max 32 warps per block
    
    int lane = GetLocalId() % 32;
    int warp_id = GetLocalId() / 32;
    
    val = warp_reduce_sum(val);
    if (lane == 0) shared_mem[warp_id] = val;
    __syncthreads();
    
    if (warp_id == 0) {
        val = (lane < (GetLocalSize() + 31) / 32) ? shared_mem[lane] : 0.0f;
        val = warp_reduce_sum(val);
    }
    return val;
}
```

## 通信算子模式

```cpp
// 调用 HCCL 集合通信
#include "hccl/hccl.h"

void allreduce_ring(GM_ADDR data, int size, int rank, int world_size) {
    // 使用 HCCL all_reduce
    HcclComm comm = get_comm();
    HcclDataType dtype = HCCL_DATA_FLOAT16;
    HcclReduceOp op = HCCL_REDUCE_SUM;
    
    hcclAllReduce(data, data, size / 2, dtype, op, comm, stream);
}
```

## 常见 AscendC 优化技巧

### 1. 128B 对齐

所有 DataCopy 的数据长度必须是 128 字节的整数倍。

```cpp
// fp16: 128B = 64 elements
constexpr int ALIGN = 64;

// 确保 tile size 对齐
static_assert(BUF_SIZE % ALIGN == 0, "BUF_SIZE must be 128B aligned");
```

### 2. 避免 Bank Conflict

```cpp
// 用 padding 避免 shared memory bank conflict
__local__ half buf[TILE_M][TILE_K + 8];  // +8 避免 stride=2的幂次时的 conflict
```

### 3. 指令级并行（ILP）

```cpp
// 展开循环，让硬件调度更多独立指令
#pragma unroll 4
for (int i = 0; i < N; i++) {
    Mul(dst[i], src1[i], src2[i], ELEM);
}
```

### 4. 精度对齐（fp32 accumulator）

```cpp
// 累加运算必须用 fp32
__local__ float acc = 0.0f;
for (int i = 0; i < K; i++) {
    acc += (float)a[i] * (float)b[i];
}
output = (half)acc;
```
