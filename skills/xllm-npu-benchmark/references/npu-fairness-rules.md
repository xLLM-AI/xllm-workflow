# NPU 公平性规则

## 硬件一致性

- 相同 NPU 型号：必须同为 910B3 (A3)
- 相同 NPU 数量：对比双方使用相同卡数
- 相同 `ASCEND_RT_VISIBLE_DEVICES`：可见设备列表一致
- 记录 NPU 驱动版本（HDK Driver >= 25.2.0）
- 性能测试前后必须保存 `npu-smi info` 和目标卡 `npu-smi info -t usages`，确认目标卡没有外部计算或未知 HBM 占用

## 软件环境

- 记录 CANN 版本（>= 8.0.RC1）
- 记录框架 commit hash
- 记录 Docker 镜像（如适用）
- 记录 Python 版本和 torch_npu 版本

## 模型配置

- 相同模型权重路径
- 相同 tokenizer 路径
- 相同精度（bf16/fp16/fp32）
- 相同量化方案（w8a8/fp8/不量化）
- 相同 `max_model_len`
- 相同 `block_size`

## 采样参数

- 相同 temperature（推荐 0 确保确定性）
- 相同 top_p、top_k
- 相同 presence/frequency penalty
- 无 streaming（或双方同时 streaming）

## 工作负载

- 相同 JSONL 数据集
- 相同 prompt 数量和顺序
- 相同 output_len 设置
- 相同场景（chat/summary/long-context）

## SLA 配置

- 相同 `max_ttft_ms`
- 相同 `max_tpot_ms`

## 搜索规则

- 每框架分别独立搜索最优配置
- 禁止将 tuned 框架与 defaults 框架比较
- 记录每次运行的完整启动命令
- 保留失败候选及失败原因
- 候选之间重启服务或清除状态
- 如果 `npu-smi info` 进程表出现 `ps` 查不到的 PID、目标卡启动前已有大额 HBM 占用、或服务空闲态 `AICore/NPU Utilization` 不稳定接近 0，本轮结果只能作为 debug/smoke 数据，不能进入正式对比
- before/after 的环境门禁信息必须一起归档；缺少门禁记录时，不要在 PR 或 skill 里写百分比收益

## 结果排序

排序优先级：
1. SLA 通过率（pass > fail）
2. 请求吞吐（requests/sec）
3. 输出 token 吞吐（tokens/sec）
4. p50 TTFT（低优先）
5. p50 TPOT（低优先）
