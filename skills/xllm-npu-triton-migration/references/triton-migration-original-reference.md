# Triton迁移指导



## 依赖

基于cann8.5.0+torch_npu2.7.1版本镜像，仅需要安装如下依赖(当前镜像已安装，可忽略)

```bash
pip install triton-ascend pybind11

```

当前torch_npu_ops目录结构如下

```bash
ops_npu/ 
custom_functions_npu/
triton_npu/
|-- CMakeLists.txt
|-- args_builder.h
|-- binary # AOT编译产物暂存目录
| |-- rope_inplace_kernel.json
| `-- rope_inplace_kernel.npubin
|-- kernel_registry.cpp
|-- kernel_registry.h
|-- operation_base.h # op基类，封装execute核心逻辑
|-- operations.h # 定义相关op
|-- setup.py # 触发AOT编译 tools
|-- test # libtorch版本接口UT
| |-- CMakeLists.txt
| |-- test_utils.h
| `-- triton_rope_inplace_test.cpp
|-- torch_api # libtorch版本接口，上层调用
| |-- npu_triton_rope_inplace.cpp # 实现算子接口定义
| |-- operation_factory.h # 工厂方法，提供调用op.execute接口
| `-- triton_ops_api.h # libtorch版本算子接口声明
`-- triton_src # triton算子源码，可通过pytest触发AOT编译
`-- test_rope_inplace.py


```

## 新算子接入

以rope_inplace算子为例，先获取python版本的triton算子源码（一般可在vllm-ascend中获取 triton kernel源码），编写相应的UT用例 以[rope_inplace](https://gitcode.com/xLLM-AI/torch_npu_ops/blob/main/triton_npu/triton_src/test_rope_inplace.py)为例

### 1.前置条件

首先我们需要识别当前triton kernel在jit编译场景下，有哪些参数会影响二进制的生成，以原生 rope_inplace_kernel为例，除了x_ptr, sin_ptr, cos_ptr外，其余变量都为标量，这些标量在 triton的pass优化里，会被进行常量折叠进kernel的二进制，所以，当标量值发生变化时，jit编 译会产生多个算子的二进制，这会导致AOT场景下无法预估算子的二进制数量。

```python
@triton.jit
def rope_inplace_kernel(
  x_ptr, # [bs, qhead, 512]
  sin_ptr,
  cos_ptr,
  x_stride,
  cos_stride,
  head_num: tl.constexpr
  hidden_size: tl.constexpr,
  rope_dim: tl.constexpr
)


```

针对这种场景，需要做一个小改动，使用do_not_specialize标记入参，让其成为一个变量，不允
许triton-ascend编译器去做常量折叠（目前没有识别到单个入参类型变化会对性能产生较大影
响）在ds模型中，一般只有tp和输入的tensor为q还是k会影响到head_num的值，x_stride一般为固定值512，cos_stride等于rope_dim = 64, hidden_size也是固定值，也就是说在模型运行过程中，只有head_num是无法预估实参的value的，所以只对这个参数做禁止特化

```python
@triton.jit(do_not_specialize=['head_num'])
def rope_inplace_kernel(
   x_ptr, # [bs, qhead, 512]
   sin_ptr,
   cos_ptr,
   head_num, # head_num q_rope and k_rope use diffrent head_num, so it need to be virant
   x_stride,
   cos_stride,
   hidden_size: tl.constexpr,
   rope_dim: tl.constexpr
   )


```

接下来编写pytest ut遍历模型运行中**所有可能会出现的输入场景**，这一步主要是为了确保kernel不会出现意外的输入场景从而导致AOT离线编译的二进制不可用

```python
@pytest.mark.parametrize("batch, head", [
(1, 8),
(4, 8),
(8, 8),
(1, 1),
(4, 1),
(8, 1)])
def test_rope_inplace(batch, head, hidden_size = 512, rope_dim = 64, itype = torch.bfloat16):
  assert rope_dim % 2 == 0
  assert hidden_size >= rope_dim
  x = torch.randn(batch, head, hidden_size, dtype = itype)
  sin = torch.randn(batch, rope_dim, dtype = itype)
  cos = torch.randn(batch, rope_dim, dtype = itype)
  out_ref = rope_ref(x, sin, cos, rope_dim)
  x_npu = x.npu()
  sin_npu = sin.npu()
  cos_npu = cos.npu()
  out_npu = triton_apply_rope_partial_inplace(x_npu, sin_npu, cos_npu)
  assert torch.allclose(out_ref, out_npu.cpu(), atol=5e-3,
  rtol=1e-2)
  print(f"test passed for rope_inplace, batch = {batch}, head = {head}, hidden_size = {hidden_size}, rope_dim = {rope_dim}")



```

当前工程下，可以使用setup.py 自动对triton_src目录下的triton kernel进行AOT编译，生成的编译产物为对应triton.jit装饰的函数签名命名的.json和.npubin文件，会自动存储在TRITON_BINARY_PATH环境变量目录下，当前默认在triton_npu/binary/目录下，**注意这里对相同命名kernel有唯一性校验，不满足会退出。**

```bash
# python setup.py
INFO: Clearing triton cache directory: /root/.triton/cache
INFO: Cleared triton cache directory: /root/.triton/cache
INFO: Running pytest on all tests under /export/home/weinan5/zhongsunj
zsj/third_party/torch_npu_ops/triton_npu ...
INFO: Running pytest in /export/home/weinan5/zhongsunjian1/xllm�zsj/third_party/torch_npu_ops/triton_npu ...
=======================================================================
starts ================================================================
platform linux -- Python 3.11.6, pytest-9.0.1, pluggy-1.6.0 -- /usr/bi
cachedir: .pytest_cache
hypothesis profile 'default'
rootdir: /export/home/weinan5/zhongsunjian1/xllm-zsj/third_party/torch_
plugins: hypothesis-6.151.2, anyio-4.9.0
collected 12 items
triton_src/test_fused_recurrent_gated_delta_rule.py::test_accuracy_fus
D128-scale1-gate_logit_normalizer0.1-torch.bfloat16] PASSED
triton_src/test_fused_recurrent_gated_delta_rule.py::test_accuracy_fus
D128-scale1-gate_logit_normalizer1-torch.bfloat16] PASSED
triton_src/test_fused_recurrent_gated_delta_rule.py::test_accuracy_fus
D128-scale1-gate_logit_normalizer0.1-torch.bfloat16] PASSED
triton_src/test_fused_recurrent_gated_delta_rule.py::test_accuracy_fus
D128-scale1-gate_logit_normalizer1-torch.bfloat16] PASSED
triton_src/test_fused_recurrent_gated_delta_rule.py::test_accuracy_fus
D128-scale1-gate_logit_normalizer1-torch.bfloat16] PASSED
triton_src/test_fused_recurrent_gated_delta_rule.py::test_accuracy_fus
D128-scale1-gate_logit_normalizer1-torch.bfloat16] PASSED
triton_src/test_rope_inplace.py::test_rope_inplace[1-8] PASSED
[ 58%]
triton_src/test_rope_inplace.py::test_rope_inplace[4-8] PASSED
[ 66%]
triton_src/test_rope_inplace.py::test_rope_inplace[8-8] PASSED
[ 75%]
triton_src/test_rope_inplace.py::test_rope_inplace[1-1] PASSED
[ 83%]
triton_src/test_rope_inplace.py::test_rope_inplace[4-1] PASSED
[ 91%]
triton_src/test_rope_inplace.py::test_rope_inplace[8-1] PASSED
[100%]
=======================================================================
21.91s ================================================================
INFO: Scanning for kernel binaries in /root/.triton/cache and its subd
INFO: Found binary:
e0vTeeXdDq39WNe9_kTi9OQ0zu08ajST8CZGgQFaikc/fused_recurrent_gated_delt
(kernel: fused_recurrent_gated_delta_rule_fwd_kernel)
INFO: Found binary: Xr9z6LT93nthtOj1MEXyhSebjGGdXwx2ZH8JTB-4_Q0/rope_i
(kernel: rope_inplace_kernel)
INFO: Scanned subdirectories, found 2 .npubin file(s)
INFO: Found 2 unique kernel(s)
INFO: Copying all found kernels to /export/home/weinan5/zhongsunjian1/
zsj/third_party/torch_npu_ops/triton_npu/binary...
INFO: Copied fused_recurrent_gated_delta_rule_fwd_kernel.npubin ->
/export/home/weinan5/zhongsunjian1/xllm�zsj/third_party/torch_npu_ops/triton_npu/binary/fused_recurrent_gated_
INFO: Copied fused_recurrent_gated_delta_rule_fwd_kernel.json ->
/export/home/weinan5/zhongsunjian1/xllm�zsj/third_party/torch_npu_ops/triton_npu/binary/fused_recurrent_gated_
INFO: Copied rope_inplace_kernel.npubin -> /export/home/weinan5/zhongs
zsj/third_party/torch_npu_ops/triton_npu/binary/rope_inplace_kernel.np
INFO: Copied rope_inplace_kernel.json -> /export/home/weinan5/zhongsun
zsj/third_party/torch_npu_ops/triton_npu/binary/rope_inplace_kernel.js
INFO: Summary - Copied: 2
INFO: Script completed successfully

```

### 2. 接入操作

#### 2.1 step1

在operations.h中添加相关Op的定义，此处构造函数的命名必须和triton-ascend中的kernel函 数签名一致

```cpp
#include "operation_base.h"

namespace xllm::kernel::npu {

class RopeInplaceOp final : public OperationBase {
public:
  RopeInplaceOp() : OperationBase("rope_inplace_kernel") {}
};
} // namespace xllm::kernel::npu


```

operationBase的定义如下，其中npubin_path标识当前kernel对应的二进制路径，用于加载对
应op的二进制并注册算子

```
namespace xllm::kernel::npu {

class OperationBase {
public:
  explicit OperationBase(std::string kernel_name,
                         std::string npubin_path = "")
      : kernel_name_(std::move(kernel_name)), npubin_path_(std::move(npubin_path)) {}
```



当前逻辑为，若构造函数传入指定路径，在注册算子时就使用构造函数提供的路径，否则会使用 TRITON_BINARY_PATH目录下的npubin文件，当前TRITON_BINARY_PATH默认定义在 CMakeLists中

```cmake
target_compile_definitions(triton_adapter PRIVATE
  TRITON_BINARY_PATH="${CMAKE_CURRENT_SOURCE_DIR}/triton_npu/binary"
)


```

```
virtual std::string resolve_npubin_path() const {
    if (!npubin_path_.empty()) {
        return npubin_path_;
    }
#ifdef TRITON_BINARY_PATH
    std::filesystem::path p(TRITON_BINARY_PATH);
    p /= (kernel_name_ + ".npubin");
    return p.string();
#else
    return {};
#endif
}
```



#### 2.2 step2

在operationFactory中定义新增Op的获取接口，这里入参的字符串仅作为key，无实际业务影响

```
class OperationFactory final {
public:
  static OperationFactory& instance() {
    static OperationFactory inst;
    return inst;
  }

  RopeInplaceOp& rope_inplace() {
    // input param is key for OperationFactory
    return get_or_create<RopeInplaceOp>("rope_inplace_kernel");
  }

private:
  OperationFactory() = default;
};
```



#### 2.3 step3

在triton_ops_api.h中添加对应libtorch版本算子接口，并添加定义文件 npu_triton_rope_inplace.cpp

```
namespace xllm::kernel::npu {

void rope_inplace(
    torch::Tensor& x,
    torch::Tensor& sin,
    torch::Tensor& cos,
    uint32_t rope_dim = 64);

} // namespace xllm::kernel::npu
```



实现rope_inplace接口，核心实现逻辑如下，对于tensor变量，将其对应的data_ptr()传入，其 余变量和python接口中保持一致即可，由于rtKernelLaunch中传入的kernelargs必须为紧凑布 局排列，且由于可能存在可选输入的kernel，所以这部分入参选择通过ArgsBuilder来动态构建， 其中**gridX, Y, Z为triton python源码中调用时的启动参数**

```cpp
int32_t gridX = bsz * head_num;
int32_t gridY = 1;
int32_t gridZ = 1;
int32_t x_stride = x.stride(0);
int32_t rope_stride = cos.stride(0);
auto npuStream = c10_npu::getCurrentNPUStream();
rtStream_t stream = static_cast<rtStream_t>(npuStream.stream());
auto& op = OperationFactory::instance().rope_inplace();
auto ret = op.execute(stream, gridX, gridY, gridZ, [&](ArgsBuilder& ab) {
  ab.constructArgs(x.data_ptr(),
  sin.data_ptr(),
  cos.data_ptr(),
  head_num, x_stride, rope_stride);
});


```

**如何确定传入参数的数量和类型？**
这一点很重要，因为triton二进制本身是一个黑盒，大部分精度异常都是入参没有传对导致的，
由于triton-ascend的pass本身会对一些可选入参做pass优化，这一部分我们无法感知到，所以
要提前知道当前kernel需要的入参有哪些，所以在进行AOT编译时，有相应的中间表示文
件.ttir，一般会存放在/root/.triton/cache目录下

```
图片显示的是 Linux 终端中的文件路径列表，其中被红框高亮选中的内容如下：

/root/.triton/cache/Xr9z6LT93ntht0iJlMEXyhSebJGGdXwx2ZH8JTB-4_Q0/rope_inplace_kernel.ttir

看起来这是 Triton 编译器生成的缓存文件路径。
```



以rope_inplace_kernel为例，对应所需的参数输入如下，其中tt.ptr对应tensor输入，i32对应 int32，float对应f32，其他数据类型类似，刚好和triton签名中 x,sin,cos,head_dum.x_stride,cos_stride数量和类型保持一致，所以在constructArgs的时候， 也需要全部构建（具体这里为什么x_stride和cos_stride没有被常量折叠的原因未知），和ttir中 的签名定义保持一致是最稳妥的做法

```
tutl.func public @rope_inplace_kernel(%arg0: !tt.ptr<bf16> (tt.divisibility = 16 : i32) loc("/export/home/weinan5/zhongsujian1/x11m-zsj/third_party/torch_npu_ops/triton_npu/triton_src/test_rope_inplace.py":7:0), %arg1: !tt.ptr<bf16> (tt.divisibility = 16 : i32) loc("/export/home/weinan5/zhongsujian1/x11m-zsj/third_party/torch_npu_ops/triton_npu/triton_src/test_rope_inplace.py":7:0), %arg2: !tt.ptr<bf16> (tt.divisibility = 16 : i32) loc("/export/home/weinan5/zhongsujian1/x11m-zsj/third_party/torch_npu_ops/triton_npu/triton_src/test_rope_inplace.py":7:0), %arg3: i32 loc("/export/home/weinan5/zhongsujian1/x11m-zsj/third_party/torch_npu_ops/triton_npu/triton_src/test_rope_inplace.py":7:0), %arg4: i32 (tt.divisibility = 16 : i32) loc("/export/home/weinan5/zhongsujian1/x11m-zsj/third_party/torch_npu_ops/triton_npu/triton_src/test_rope_inplace.py":7:0), %arg5: i32 (tt.divisibility = 16 : i32) loc("/export/home/weinan5/zhongsujian1/x11m-zsj/third_party/torch_npu_ops/triton_npu/triton_src/test_rope_inplace.py":7:0), %arg6: i32 (tt.divisibility = 16 : i32) loc("/export/home/weinan5/zhongsujian1/x11m-zsj/third_party/torch_npu_ops/triton_npu/triton_src/test_rope_inplace.py":7:0)) attributes {noinline = false} {
  %cst = arith.constant dense<0.000000e+00> : tensor<64xf32> loc(#loc1)
  %0 = arith.constant dense<0.000000e+00> : tensor<32xf32> loc(#loc1)
```



#### 2.4 step4

添加相关编译文件

```
添加相关编译文件

set(TRITON_NPU_API_SRCS
triton_npu/torch_api/npu_triton_rope_inplace.cpp
)
```



### 3. 验证

可以在triton_npu/test目录下添加相应的UT用例 当前标准用法是手动调用register_kernel注册算子，**这一步可以指定实际的算子二进制path（相 应的json文件也要保存在同级目录下）**，不调用的话，会在第一次进行op.execute时使用**2.1**中 提到的TRITON_BINARY_PATH去加载

```cpp
void SetUp() override {
try {
  torch::zeros({1}, torch::TensorOptions().device("npu:0"));
  tensor_options_ =
  torch::TensorOptions().dtype(torch::kBFloat16).device("npu:0");
  npu_available_ = true;
} catch (...) {
  tensor_options_ =
  torch::TensorOptions().dtype(torch::kBFloat16).device(torch::kCPU);
  npu_available_ = false;
  return;
}
  kernel_name_ = "rope_inplace_kernel";
  binary_filename_ = "rope_inplace_kernel.npubin";
  torch::manual_seed(42);
  torch_npu::init_npu(device_str_);
  /* 21-26 can be deleted */
  binary_path_ = GetKernelBinaryPath(binary_filename_);
  auto& reg = KernelRegistry::get_instance();
  ASSERT_TRUE(reg.register_kernel(kernel_name_, binary_path_)) << "Failed to register kernel: " << kernel_name_ << " from "
  << binary_path_;
  ASSERT_NE(reg.get_kernel_stub(kernel_name_), nullptr) << "Failed to get kernel stub: " << kernel_name_;
}



```

添加CMake

```cmake
cc_test(
NAME
  rope_inplace_test
SRCS
  triton_rope_inplace_test.cpp
DEPS
  GTest::gtest
  GTest::gtest_main
  triton_adapter
  torch
  torch_npu
)
target_compile_definitions(rope_inplace_test PRIVATE
  TEST_BINARY_DIR="${BINARY_DIR}"
)

```

运行ut后，精度正常，测试通过



# ATB版本

[ATB triton接入demo](https://gitee.com/vallenChen/cann-atb-graphop-demo/tree/access_triton/examples/atb_plugin/plugin_triton_operations/src)

其中核心操作是添加config.json 和 实现atb::OperationInfra的子类
在config/triton_tactic_info.json中添加对应的kernelname和path，用于注册算子的二进制文件

```json
{
    "SplitRmsnormRopeFP32QH1024KVH128WithBiasKernel" :
    {
        "ops": "split_qkv_rmsnorm_rope_kernel",
        "path": "/" 
    },

    "SplitRmsnormRopeFP32QH1024KVH128WithoutBiasKernel" :
    {
        "ops": "split_qkv_rmsnorm_rope_kernel",
        "path": "/" 
    }
}

```

实现SplitRmsnormRopeOperation类

```cpp
// 用于路由多个同op不同输入的triton kernel的atb param参数
struct SplitRmsnormRopeParam {
    // A flag indicating whether the model use bias
    bool hasBias = false;
};

// 构造输入参数结构体，取决于triton kernel的kernel参数原型
struct __attribute__((packed)) SplitRmsnormRopeArgs {
    void *fftsAddr = nullptr;
    void *syncBlockLock = nullptr;
    void *workspaceAddr;
    void *input;
    void *sin;
    void *cos;
    void *qOutput;
    void *kOutput;
    void *vOutput;
    void *qWeight;
    void *qBias = nullptr;
    void *kWeight;
    void *kBias = nullptr;
    int32_t batchSize; // 其中constexpr的参数可以不需要传
    int32_t gridX;
    int32_t gridY;
    int32_t gridZ;
};

class SplitRmsnormRopeOperation : public atb::OperationInfra {
public:
    explicit SplitRmsnormRopeOperation(const std::string &name, SplitRmsnormRopeParam param);
    ~SplitRmsnormRopeOperation() override;
    std::string GetName() const override;
    // 实现算子shape推导
    atb::Status InferShape(const atb::SVector<atb::TensorDesc> &inTensorDescs,
        atb::SVector<atb::TensorDesc> &outTensorDescs) const override;
    // 返回算子入参数量
    uint32_t GetInputNum() const override;
    // 返回算子出餐数量
    uint32_t GetOutputNum() const override;
    // 主要负责算子调用前的workspace_size 读取， grid参数计算，以及一些常量的计算
    atb::Status Setup(const atb::VariantPack &variantPack, uint64_t &workspaceSize, atb::Context *context) override;
    // 使用rtkernelLaunch 下发算子
    atb::Status Execute(const atb::VariantPack &variantPack, uint8_t *workspace, uint64_t workspaceSize,
        atb::Context* context) override;

private:
    std::string name_;
    SplitRmsnormRopeParam param_;
    SplitRmsnormRopeArgs args_;
    KernelInfo kernelInfo_;
    uint32_t blockNum_ = 0;
};



```

execute函数实现举例， 其中rtkernelLaunch中会生成我们定义好的算子Args类，并通过ATB输入的variantPack中tensor类型的deviceData获取输入的device addr，将其赋值给args，传入rtKernelLaunch。

```cpp
atb::Status SplitRmsnormRopeOperation::Execute(const atb::VariantPack &variantPack, uint8_t *workspace, uint64_t workspaceSize, atb::Context* context)
{
    std::cout << "SplitRmsnormRopeOperation Execute start" << std::endl;
    // 只将准备好的args、handle下发
    void *fftsAddr = nullptr;
    uint32_t fftsLen;
    int ret = rtGetC2cCtrlAddr((uint64_t*)&fftsAddr, &fftsLen);
    if (ret != 0) {
        std::cerr << "rtGetC2cCtrlAddr failed, error code: " << ret << std::endl;
        return atb::ERROR_RT_FAIL;
    }
    args_.fftsAddr = fftsAddr;
    args_.workspaceAddr = workspace;
    args_.input = variantPack.inTensors.at(0).deviceData;
    args_.sin = variantPack.inTensors.at(1).deviceData;
    args_.cos = variantPack.inTensors.at(2).deviceData;
    args_.qOutput = variantPack.outTensors.at(0).deviceData;
    args_.kOutput = variantPack.outTensors.at(1).deviceData;
    args_.vOutput = variantPack.outTensors.at(2).deviceData;
    args_.qWeight = variantPack.inTensors.at(3).deviceData;
    args_.kWeight = variantPack.inTensors.at(4).deviceData;
    args_.batchSize = static_cast<int32_t>(variantPack.inTensors.at(0).desc.shape.dims[0]);

    ret = rtKernelLaunch(kernelInfo_.funcStubHandle, blockNum_, static_cast<void *>(&args_), sizeof(args_), NULL, context->GetExecuteStream());
    if (ret != 0) {
        std::cerr << "rtKernelLaunch failed, error code: " << ret << std::endl;
        return atb::ERROR_RT_FAIL;
    }
    std::cout << "SplitRmsnormRopeOperation Execute end" << std::endl;
    return atb::NO_ERROR;
}


```

# 问题记录

## 1. fused_recurrent_gated_delta_rule二进制kernel数目异常问题

在vllm-ascend中，这个triton_kernel的定义如下

```
@triton.jit(do_not_specialize=['N', 'T'])
def fused_recurrent_gated_delta_rule_fwd_kernel(
    q,
    k,
    v,
    g,
    beta,
    o,
    h0,
    ht,
    cu_seqlens,
    ssm_state_indices,
    num_accepted_tokens,
    scale,
    N: tl.constexpr,  # num of sequences
    T: tl.constexpr,  # num of tokens
    B: tl.constexpr,
    H: tl.constexpr,
    HV: tl.constexpr,
```



其中注解上添加了相应的注解选项，但是二进制数目始终会随着T,N的不同发生变化，故想探究根因

`do_not_specialize=['N', 'T']` **会显著减少 kernel 二进制的编译次数****，因为它阻止 Triton 因 `N` 或 `T` 的值不同而生成新的 kernel。经求证，triton-ascend并不会对这部分注解做任何修改

### 试验分析

```
代码部分：

@triton.jit(do_not_specialize=['N'])
def triton_test_kernel(
    x,
    N: tl.constexpr
):
    i_k, i_v, i_nh = tl.program_id(0), tl.program_id(1), tl.program_id(2) # 注意：这里被遮挡了一部分，根据上下文推测是 program_id(2)

    def test_triton_kernel():
        case = [1, 2]
        grid = (4, 1, 1)
        x = torch.zeros(1).npu()
        for i in case:
            triton_test_kernel[grid](x, i)

if __name__ == "__main__":
    test_triton_kernel()
终端部分：

root@07455a095062:~/.triton/cache# rm -rf *
root@07455a095062:~/.triton/cache# cd -
/home/z00881607/triton-workspace/triton_loader_demo
root@07455a095062:/home/triton-workspace/triton_loader_demo# python triton_test.py
root@07455a095062:/home/triton-workspace/triton_loader_demo# cd -
root@07455a095062:~/.triton/cache# find . -name *npubin
/V7vIT3z_zN9Hm9mzoKOsE0tM2DT5wwySomZ1NaCmVes/triton_test_kernel.npubin
/hmrfxN16qtsmfgolXQkWcyAFEt7FfSIJqUI_WyEi0HQ/triton_test_kernel.npubin
```



在排除无关变量后，依然生成了2个对应的kernel，与预期不符
上述试验发现，只要输入的N为标量，那么triton就会生成多个二进制，猜测是triton的编译优化，做常量的折叠

### 问题根因

在jit的源码中进行分析，发现tl.constexpr和do_not_specialize是相互互斥的，但是没有报错原因未知

最终通过不加tl.constexpr但是加上注解
最终只生成了一个kernel，符合预期

## 2. fused_recurrent_gated_delta_rule封装torch接口精度异常

### 问题现象

参考vllm-ascend的pytorch版本接口，封装triton-ascend kernel的libtorch版本在单测case下精度异常，其中有两个输出tensor， o一直为0，final_state为异常值， 测试用例如下， 分别调用自封装的接口`npu_fused_recurrent_gated_delta_rule`和libtorch的golden`torch_recurrent_gated_delta_rule`，并对输出进行比对。

```cpp
TEST_F(TritonRecurrentGatedDeltaRuleTest, MultiBatchTest) {
  if (!npu_available_) {
    GTEST_SKIP() << "NPU device not available";
  }

  auto device = at::Device(device_str_);
  constexpr int64_t batch = 4;
  constexpr int64_t T = 1;
  constexpr int64_t num_heads = 4;
  constexpr int64_t num_v_heads = 8;
  constexpr int64_t k_head_dim = 128;
  constexpr int64_t v_head_dim = 128;
  constexpr bool use_qk_l2norm_in_kernel = true;

  torch::manual_seed(0);
  auto dtype = torch::kFloat16;
  auto L = batch * T;

  auto q = torch::randn({batch, T, num_heads, k_head_dim}, dtype);
  auto k = torch::randn({batch, T, num_heads, k_head_dim}, dtype);
  auto v = torch::randn({batch, T, num_v_heads, v_head_dim}, dtype);
  auto g = torch::randn({batch, T, num_v_heads}, torch::kFloat32);
  auto beta = torch::randn({batch, T, num_v_heads}, torch::kFloat32);
  auto initial_state = torch::randn({batch, num_v_heads, k_head_dim, v_head_dim}, torch::kFloat32);

  torch::Tensor q_expanded = q, k_expanded = k;
  if (num_v_heads / num_heads > 1) {
      q_expanded = q.repeat_interleave(num_v_heads / num_heads, 2);
      k_expanded = k.repeat_interleave(num_v_heads / num_heads, 2);
  }

  auto [golden_o, golden_state] = torch_recurrent_gated_delta_rule(
    q_expanded, k_expanded, v, g, beta,
    initial_state,
    true,
    true
  );

  // Apply correct reshape operations as in original test
  auto q_d = q.reshape({1, L, num_heads, k_head_dim}).to(device);
  auto k_d = k.reshape({1, L, num_heads, k_head_dim}).to(device);
  auto v_d = v.reshape({1, L, num_v_heads, v_head_dim}).to(device);
  auto g_d = g.reshape({1, L, num_v_heads}).to(device);
  auto beta_d = beta.reshape({1, L, num_v_heads}).to(device);
  auto init_d = initial_state.to(device);

  // Create cu_seqlens [0, 1, 2, ..., batch] as in original test
  std::vector<int64_t> culen;
  culen.reserve(batch + 1);
  for (int i = 0; i <= batch; ++i) {
      culen.push_back(i);
  }
  auto cu_seqlens = torch::tensor(culen, torch::kInt64).to(device);

  // Calculate scale factor
  float scale_val = 1.0f / std::sqrt(static_cast<float>(k_head_dim));
  auto npu_stream = c10_npu::getCurrentNPUStream(kDeviceId);

  // Call NPU kernel 
  auto [o_d, state_d] = npu_fused_recurrent_gated_delta_rule(
      q_d, k_d, v_d, g_d,
      beta_d,
      scale_val,
      init_d,
      false,
      cu_seqlens,
      c10::nullopt,
      c10::nullopt,
      use_qk_l2norm_in_kernel
  );
  aclrtSynchronizeStream(npu_stream.stream());

  // Reshape output to match golden implementation shape
  auto o = o_d.cpu().reshape(golden_o.sizes());
  auto state = state_d.cpu();

  // Compare results
  auto output_diff = (golden_o - o).abs().max().item<float>();
  EXPECT_LT(output_diff, 1e-3) 
      << "Output mismatch: max diff = " << output_diff
      << ", shape: " << o.sizes()
      << ", golden range [" << golden_o.min().item<float>() << ", " << golden_o.max().item<float>() << "]"
      << ", actual range [" << o.min().item<float>() << ", " << o.max().item<float>() << "]";

  auto state_diff = (golden_state - state).abs().max().item<float>();
  EXPECT_LT(state_diff, 1e-2)
      << "State mismatch: max diff = " << state_diff
      << ", shape: " << state.sizes()
      << ", golden state range [" << golden_state.min().item<float>() << ", " << golden_state.max().item<float>() << "]"
      << ", actual state range [" << state.min().item<float>() << ", " << state.max().item<float>() << "]";
}


```

### 定位过程

1. 如果输出都为全0值，可能存在kernel未被正常拉起的可能性，但问题现象是只有一个为0值，所以先排除这部分可能性, 使用`msprof op xxx`拉起测试程序，发现采集到了对应的kernel信息，故排除kernel未拉起原因
2. 怀疑可能是libtorch版本的golden函数写错的原因，为排除这部分影响，需要保证python和c侧的输入保持一致，这部分由于libtorch和pytorch dump下来的pt文件格式有不同，所以`torch.save`下来的tensor无法被`torch::load`使用，所以需要借助npy来进行中转，这部分需要使用`cnpy`库文件，仅需编译的时候引入即可，相关使用的辅助函数如下
   定位结论：输入的dtype和shape信息已全部对齐，libtorch的golden也与pytoch对齐，tl.constexpr变量也计算一致， 排除相关原因
3. 由于fused_gdn_gating算子能够跑通，所以初步怀疑可能会存在什么差异，发现pytorch版本fused_recurrent_gated_delta_rule中存在可选输入，所以libtorch版本的接口也继承了这一特点

继续观察tritona-ascend的相关中间结果，发现ttir文件中，第10，11个参数本来应该对应的是triton kernel中的ssm_state_indices和num_accepted_tokens，这两个输入在非mtp场景为None，但是ttir文件中第10和第11个参数是f32 和 i32，猜测对应float32，和int32，而非预期的tt.ptr<f32>数据类型，所以猜测triton编译器把None输入的tensor地址入参给优化了。</f32>
故直接在传参的时候，忽略这两个可选输入地址，重新运行测试用例，精度正常。

### 问题根因

将wrapper_src生成的代码dump下后，发现问题根因，虽然生成的launch接口，是带有可选参数的，但是实际传入的args里是不带可选输入的，这就是最终的问题根因

# debug技巧

libtorch的tensor输入一般比较难和pytorch的tensor做对比，所以初步排查可以通过下面的打印函数，打印一下tensor的基本信息，检查输入的数据类型、shape和是否连续等信息排除整网的精度问题

```cpp
inline void print_tensor_info(const torch::Tensor& tensor, const std::string& name = "Tensor") {
    std::cout << "=== " << name << " Information ===" << std::endl;
    // 基本形状信息
    std::cout << "Shape: [";
    for (int64_t i = 0; i < tensor.dim(); ++i) {
        std::cout << tensor.size(i);
        if (i < tensor.dim() - 1) std::cout << ", ";
    }
    std::cout << "]" << std::endl;
    // 维度数量
    std::cout << "Dimensions: " << tensor.dim() << std::endl;
    // 总元素数量
    std::cout << "Num elements: " << tensor.numel() << std::endl;
    // 数据类型
    std::cout << "Dtype: " << tensor.scalar_type() << std::endl;
    // 设备信息
    std::cout << "Device: " << tensor.device() << std::endl;
    // 是否连续内存
    std::cout << "Is contiguous: " << std::boolalpha << tensor.is_contiguous() << std::endl;
    // 是否有梯度
    std::cout << "Requires grad: " << std::boolalpha << tensor.requires_grad() << std::endl;
    // 内存布局 (stride)
    if (tensor.dim() > 0) {
        std::cout << "Strides: [";
        for (int64_t i = 0; i < tensor.dim(); ++i) {
            std::cout << tensor.stride(i);
            if (i < tensor.dim() - 1) std::cout << ", ";
        }
        std::cout << "]" << std::endl;
    }
    // 内存大小（字节）
    std::cout << "Memory size (bytes): " << tensor.nbytes() << std::endl;
    // 是否被定义（不是空张量）
    std::cout << "Is defined: " << std::boolalpha << tensor.defined() << std::endl;
    // 数据指针（可选，主要用于调试）
    std::cout << "Data pointer: " << tensor.data_ptr() << std::endl;
    std::cout << "==========================" << std::endl;
}



```

# 后续工作

当前`torch_npu_ops`中`triton_npu`框架存在内核复用效率问题。不同模型在使用同一算子时，常因张量并行（TP）切分策略不同导致部分常量（如切分尺寸）被编译时折叠进二进制，生成无法共享的内核。一个直接的解决方案可参考2.1的内容，将相关常量转为变量以避免编译时绑定，但这可能引入运行时性能开销。

然而，更深层挑战在于入参结构的可变性。当不同模型对同一算子传入不同数量的可选参数时（如部分场景省略了某些高级参数），即便内核逻辑完全一致，当前框架仍需为每种入参组合生成不同名称的内核。现有接口缺乏一个动态路由层，无法根据实际入参智能匹配并复用最合适的预编译内核，现缺少一个类似“内核选择器（BestKernel Selector）”的组件来屏蔽入参差异，实现内核接口代码的复用。解决这一问题将是后续的重要工作方向之一。