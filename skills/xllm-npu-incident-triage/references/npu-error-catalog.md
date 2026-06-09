# NPU 错误码目录

## 错误码分类

| 范围 | 模块 |
|------|------|
| 0x0000-0x0FFF | 系统级 |
| 0x1000-0x1FFF | 运行时 (rt) |
| 0x2000-0x2FFF | 驱动 (drv) |
| 0x3000-0x3FFF | AICore/CCE |
| 0x5000-0x5FFF | HCCL 通信 |
| 0x8000-0x8FFF | 内存管理 |

## 常见错误码

### AICore 算子错误 (E3xxxx)

| 错误码 | 名称 | 描述 | 常见原因 | 解决建议 |
|--------|------|------|---------|---------|
| E30001 | RT_ERROR_INVALID_PARAM | 输入参数错误 | dtype/shape 不匹配 | 检查算子输入参数 |
| E30002 | RT_ERROR_NOT_SUPPORT | 不支持的操作 | 算子不支持当前输入 | 检查算子支持列表 |
| E39999 | AICore timeout | AICore 执行超时 | 算子实现 bug 或硬件问题 | 查看 dmesg 驱动日志 |
| E30010 | AICORE_ECODE_FAIL | AICore 执行失败 | 算子内部异常 | dump 算子输入输出 |

### 通信错误 (E5xxxx)

| 错误码 | 名称 | 描述 | 常见原因 | 解决建议 |
|--------|------|------|---------|---------|
| E50000 | HCCL_TIMEOUT | 通信超时 | 节点断连、ROCE 问题 | 检查网络、跑 hccl_test |
| E50001 | HCCL_E_INTERNAL | HCCL 内部错误 | CANN 版本不匹配 | 确认所有节点 CANN 版本一致 |
| E50010 | HCCL_E_PARA | HCCL 参数错误 | world_size/rank 配置错误 | 检查 TP/PP 配置 |

### 内存错误 (E8xxxx)

| 错误码 | 名称 | 描述 | 常见原因 | 解决建议 |
|--------|------|------|---------|---------|
| E82000 | MEMORY_NOT_ENOUGH | 显存不足 | 模型过大/显存碎片 | 增加卡数、降低利用率配置 |
| E82001 | KVCACHE_ALLOC_FAIL | KV Cache 分配失败 | block 耗尽或碎片 | 减少并发数、调大显存利用率 |

### 图编译错误 (E4xxxx)

| 错误码 | 名称 | 描述 | 常见原因 | 解决建议 |
|--------|------|------|---------|---------|
| E40010 | GE_COMPILE_FAIL | 图编译失败 | 不支持的算子或 shape | 检查 GE 编译日志 |
| E40020 | GE_REPLAY_FAIL | Graph replay 失败 | shape 变化未适配 | 检查动态 shape 分桶 |

### 系统级错误

| 错误码 | 名称 | 描述 | 常见原因 | 解决建议 |
|--------|------|------|---------|---------|
| E10001 | DEVICE_NOT_FOUND | NPU 设备未找到 | 驱动问题/设备不可见 | npu-smi info、检查 ASCEND_RT_VISIBLE_DEVICES |
| E10002 | DEVICE_BUSY | NPU 被占用 | 其他进程占用 | 杀掉其他进程或换设备 |

### torch_npu 自定义算子错误 (aclnn)

| 错误码 | 名称 | 描述 | 常见原因 | 解决建议 |
|--------|------|------|---------|---------|
| 561002 | aclnnAddRmsNorm shape mismatch | AddRmsNorm tiling 失败 | x1/x2 shape 不匹配 (residual connection) | 检查 MTP/draft model hidden_dim 是否与 target 一致; torch_npu 版本是否支持 MTP |

## 错误排查流程

```
1. 从日志获取完整错误码（如 E39999）
2. 查本表确定错误分类
3. 按 "常见原因" 逐条排查
4. 如需深入，使用：
   - dmesg | grep -i ascend    # 驱动日志
   - nvidia-smi 等效: npu-smi info
   - ascend-dmi                 # NPU 诊断工具
5. 参考华为昇腾论坛 hiascend.com/forum
```
