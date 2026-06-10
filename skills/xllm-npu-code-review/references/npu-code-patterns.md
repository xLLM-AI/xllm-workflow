# NPU 代码模式规范

## C++ 引擎代码

### 资源管理

```cpp
// DO: RAII for NPU resources
class NpuBuffer {
public:
    NpuBuffer(size_t size) {
        rtMalloc(&ptr_, size, RT_MEMORY_DDR);
    }
    ~NpuBuffer() {
        if (ptr_) rtFree(ptr_);
    }
    void* data() const { return ptr_; }
private:
    void* ptr_ = nullptr;
};

// DON'T: raw malloc without cleanup
void* ptr = malloc(size);
// ... no cleanup on exception
```

### 错误处理

```cpp
// DO: check rtError in all NPU API calls
rtError_t ret = rtMemcpy(dst, src, size, RT_MEMCPY_DEVICE_TO_DEVICE);
if (ret != RT_ERROR_NONE) {
    SPDLOG_ERROR("rtMemcpy failed: {}", static_cast<int>(ret));
    return Status::NPU_ERROR;
}

// DON'T: ignore rtError
rtMemcpy(dst, src, size, RT_MEMCPY_DEVICE_TO_DEVICE);  // unchecked
```

### 多线程安全

```cpp
// DO: use mutex for shared KV cache state
class KVCacheManager {
    std::mutex mu_;
    std::deque<int> free_blocks_;
public:
    int alloc_block() {
        std::lock_guard<std::mutex> lock(mu_);
        if (free_blocks_.empty()) return -1;
        int block = free_blocks_.front();
        free_blocks_.pop_front();
        return block;
    }
};
```

## TileLang 算子

### Tiling 策略

```python
# DO: explicit tiling with UB budget awareness
def build_matmul_kernel(M, N, K, block_M=128, block_N=128, block_K=64):
    # A3 UB size: 2MB per AICore
    # Ensure block_M * block_K * 2 + block_K * block_N * 2 < 2MB
    ...

# DON'T: arbitrary tiling without UB calculation
def build_matmul_kernel(M, N, K, block_M=256, block_N=256, block_K=256):
    # May exceed UB capacity on A3
    ...
```

### Precision Alignment

```python
# DO: explicit cast in kernel for mixed precision
@T.prim_func
def rope_kernel(q, k, cos, sin, out_q, out_k):
    # Cast to fp32 for trigonometric operations
    cos_fp32 = T.tile.cast(cos, "float32")
    sin_fp32 = T.tile.cast(sin, "float32")
    # Compute in fp32
    q_fp32 = T.tile.cast(q, "float32")
    # Cast back to original dtype
    out_q = T.tile.cast(result, "float16")
```

## AscendC 算子

### Double Buffer

```cpp
// DO: use double buffer for MTE2 + AICore overlap
__global__ void vec_add_kernel(GM_ADDR x, GM_ADDR y, GM_ADDR z, int size) {
    __local__ half x_local[2][BLOCK_SIZE];  // double buffer
    __local__ half y_local[2][BLOCK_SIZE];
    
    int buf_idx = 0;
    for (int i = 0; i < size; i += BLOCK_SIZE) {
        // Load next block asynchronously
        CopyIn(buf_idx, x + i, x_local[buf_idx]);
        CopyIn(buf_idx, y + i, y_local[buf_idx]);
        
        // Compute on previous block
        Compute(x_local[1-buf_idx], y_local[1-buf_idx]);
        CopyOut(z + i - BLOCK_SIZE);
        
        buf_idx = 1 - buf_idx;
    }
}
```

## 图模式兼容

```cpp
// DO: register operator for GE compilation
XLLM_REGISTER_OP(MyCustomOp)
    .Input("x: float16")
    .Output("y: float16")
    .Attr("scale: float")
    .SetShapeFn([](InferContext* ctx) {
        ctx->SetOutput(0, ctx->Input(0));
    });

// DON'T: use Python-only operations that break graph compilation
// These cause graph break:
// - dynamic shape operations (in graph mode)
// - Python data-dependent control flow
// - operations without GE op implementation
```
