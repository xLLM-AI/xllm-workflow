# xLLM NPU 算子工作中文 Prompts

## 场景 1：外部算子迁移到 xLLM

```text
请根据来源实现选择最窄的专项 skill，把 <operator> 从 <source_repo_or_impl> 迁移到 xLLM NPU 路径。

输入：
- 来源实现：<PyTorch | torch_npu | Triton-Ascend | AscendC | ATB | xllm_ops>
- xLLM 目标路径：<target_module_or_file>
- 代表 shape：<shape_list>
- dtype/layout：<dtype_and_layout>
- 正确性参考：<reference_op_or_test>
- artifact root：<run_root>

流程：
1. 先用 profiling 证明该算子路径确实是瓶颈。
2. 盘点来源算子的语义：shape、dtype、layout、stream、workspace、in-place、graph 兼容性。
3. 选择专项入口：Triton-Ascend 使用 xllm-npu-triton-migration；已有 xllm_ops 接入 runtime 使用 xllm-npu-xllm-ops-integration；其他来源优先使用目标仓本地 skill 或成熟库接入。
4. 定义 xLLM 接口契约：输入输出 tensor、shape 约束、错误处理、fallback。
5. 选择最低风险路径接入：优先复用成熟库，再考虑自定义 kernel。
6. 添加 focused correctness test 和端到端 smoke。
7. 对比算子级性能和模型级性能。
8. 记录迁移风险、失败尝试和可复用 shape 经验。
```

## 场景 2：torch_npu 融合算子替换

```text
请分析 <xllm_path> 中的 <operator_pattern> 是否可以替换为 torch_npu 融合算子。

要求：
1. 从 profiling 五表确认该 pattern 是性能瓶颈。
2. 对齐 torch_npu 算子的输入输出、shape、dtype、layout、广播、in-place 语义。
3. 检查 graph 模式、动态 shape、stream 和 workspace 是否兼容。
4. 实现最小替换 patch，并保留安全 fallback。
5. 用 10 条 deterministic prompt 做精度 smoke。
6. 跑 warmed-up 性能评测和 follow-up profiling，确认收益来源。
```

## 场景 3：Triton-Ascend AOT 接入评估

```text
请使用 xllm-npu-triton-migration，评估 <operator> 是否适合 Triton-Ascend AOT 接入。

输入：
- 目标 shape：<shape_list>
- 期望收益：<target_gain>
- 当前热点 kernel：<profile_kernel_names>
- 正确性参考：<reference_impl>

判断：
1. shape 是否稳定，是否适合 AOT 编译。
2. dtype/layout 是否匹配 Triton-Ascend 支持范围。
3. 编译产物如何纳入 xLLM 构建和发布。
4. runtime dispatch 如何选择 shape specialization。
5. 与 AscendC / torch_npu 路径相比，维护风险是否可接受。

输出 go/no-go 结论和验证计划。
```

## 场景 4：xllm_ops runtime 接入

```text
请使用 xllm-npu-xllm-ops-integration，把 third_party/xllm_ops 中已经完成 build、wrapper 或精度验证的 <operator> 接入 xLLM runtime。

输入：
- xllm_ops 路径：<third_party/xllm_ops_path>
- op 名称：<op_name>
- API 符号：<api_symbol>
- aclnn 名称：<aclnn_name_if_any>
- runtime callsite：<xllm_runtime_path>
- 验证范围：<static | build | op_accuracy | xllm_smoke | e2e_accuracy | performance>

要求：
1. 补齐 xLLM wrapper、xllm_ops_api.h、CMake 和上层 callsite。
2. 保留 unsupported shape/dtype/layout 的 fallback 或明确替换边界。
3. 先跑静态 harness，再跑最小 build、smoke、精度和性能验证。
4. 输出接入报告，说明 custom OPP、graph/dynamic shape 和 host sync 风险。
```

## 场景 5：AscendC 自定义算子接入

```text
请为 <operator> 设计 AscendC 自定义算子接入方案。

要求：
1. 明确 op_host、op_kernel、CMake、wrapper、EXEC_NPU_CMD 的接入点。
2. 给出 tensor shape 示例，说明每个维度的含义。
3. 说明 workspace、tiling、block、UB、alignment 和 dtype 限制。
4. 设计单元测试：正常 shape、边界 shape、非法参数、graph 模式。
5. 设计性能验证：算子级 benchmark + 模型端到端 benchmark。
6. 先输出方案，不要在 profiling 未证明收益前直接写 kernel。
```

## 场景 6：kernel-pilot 准入判断

```text
请判断 <operator> 是否满足 kernel-pilot 准入条件。

准入条件：
- xLLM 在非 kernel 优化后仍未达到目标。
- profiling 显示该 kernel 族解释了至少 1% 的相关阶段时间，或是明确的长尾阻塞。
- 有稳定正确性参考。
- 代表 shape 覆盖生产路径。
- 自研 kernel 的收益/风险优于复用已有融合算子或库算子。

如果任一条件不满足，请输出 no-go 报告，并给出更安全的替代优化路径。
```

## 场景 7：算子迁移后的回归验证

```text
请验证 <operator> 迁移 patch 是否可合入。

验证项：
1. 编译和相关 UT 通过。
2. 算子级 correctness：与 reference 输出误差在阈值内。
3. 端到端精度：固定 prompt smoke + 目标数据集子集。
4. 性能：warmed-up baseline/current 对比。
5. profiling：目标 kernel 或 dispatch 事件按预期变化。
6. fallback：不支持 shape/dtype 时行为明确，不产生静默错误。

输出合入建议、风险点和需要写入 model PR history 的经验。
```
