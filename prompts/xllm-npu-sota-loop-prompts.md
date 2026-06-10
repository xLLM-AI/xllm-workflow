# xLLM NPU SOTA Loop 中文 Prompts

## 场景 1：端到端性能优化闭环

```text
请使用 xllm-npu-sota-loop，对 <target_framework> 在昇腾 <A2_or_A3> 上进行端到端性能优化。

目标：
- 模型：<model_name>
- 框架：<xllm | vllm-ascend | sglang-npu>
- 对照框架：<baseline_frameworks>
- workload：输入 <input_tokens> token，输出 <output_tokens> token，parallel=<parallel>，number=<number>
- 采样参数：temperature=<temperature>，top_p=<top_p>，top_k=<top_k>，ignore_eos=<true_or_false>
- 优化指标：<TPOT | TTFT | TPS> 相对当前 baseline 提升 <target_percent>%
- artifact root：<run_root>

执行要求：
1. 先记录环境、模型、commit、启动命令、evalscope 命令和 NPU 状态。
2. 修改代码前必须采集带 warmup 的 baseline 性能数据。
3. 修改代码前必须采集能解释瓶颈的 profiling，profiling run 不直接当正式性能结论。
4. 查询 model-pr-optimization-history，确认历史上是否已有类似优化或失败经验。
5. 每轮 evidence loop 只实现一个可验证优化点。
6. 每轮都执行 code review、精度验证、带 warmup 的性能验证；必要时补 profiling。
7. 达到目标或满足停止条件后，输出最终对比表和经验沉淀位置。
```

## 场景 2：TPOT 目标优化到指定阈值

```text
请使用 xllm-npu-sota-loop，把 <model_name> 在 <hardware> 上的 TPOT 优化到 <target_tpot_ms> ms 以内。

固定条件：
- 不开启 MTP：<true_or_false>
- TP：<tp_size>
- 输入/输出：<input_tokens>/<output_tokens>
- 并发：<parallel>
- warmup：<warmup_num>
- 服务启动脚本：<server_script>
- 评测脚本或命令：<eval_command>

流程：
1. 先跑 baseline，输出 TTFT/TPOT/TPS、P50/P90/P99、NPU 空闲情况。
2. 采集 decode-focused profiling，重点看两轮 decode 中间的 hostbound gap。
3. 给出候选优化点排序：预期收益、风险、修改文件、验证方式。
4. 实现收益最高且风险最低的一项，验证精度和性能。
5. 若未达到 <target_tpot_ms> ms，继续下一轮，不要在没有数据时停。
6. 每轮记录成功/失败原因，最终更新 run ledger 或 skill reference。
```

## 场景 3：decode 空泡专项分析

```text
请使用 xllm-npu-profiler 和 xllm-npu-pipeline-analysis，分析 <model_name> 的 decode 空泡。

输入：
- baseline 性能目录：<baseline_perf_path>
- current 性能目录：<current_perf_path>
- profiling 目录：<profiling_path>
- 关注 timeline anchor：replaceToken、GatherV2、graph replay、PagedAttention、HCCL、StreamWaitEvent

输出：
1. 单步 decode 阶段表：host 准备、graph replay、attention、postprocess、通信、结果回传。
2. 两轮 decode 间隔表：上一轮结束点、下一轮开始点、gap 大小、主要事件。
3. 判断真正推迟下一轮 GatherV2 的原因。
4. 给出可落地优化方案：是否能提前下发、是否能消除同步、是否能融合 copy/fill。
5. 给出验证计划：非 profiling 性能 run + follow-up profiling + 精度 smoke。
```

## 场景 4：MTP 接受率与性能回归验证

```text
请使用 xllm-npu-eval-runner、xllm-npu-benchmark 和 xllm-npu-accuracy-debug，验证 <model_name> 的 MTP 接受率是否回归。

对比对象：
- 历史代码：<good_commit_or_branch>
- 当前代码：<current_commit_or_branch>
- MTP 配置：num_speculative_tokens=<n>，draft_model=<draft_model_path>
- 固定 prompt 集：<prompt_dataset_path>

要求：
1. 使用完全相同的一批 prompt，不要每次随机生成不同输入。
2. 评测前后抓服务端 counter：
   - speculative_num_accepted_tokens_total
   - speculative_num_draft_tokens_total
3. 不要只依赖 evalscope 或客户端估算的接受率。
4. 同时输出 TTFT/TPOT/TPS 和真实服务端接受率。
5. 如果接受率下降，分析是 draft 权重、validate 路径、graph 参数、chunk prefill、采样参数还是模型路径引入。
6. 用 5-10 条 deterministic prompt 做精度 smoke，必要时扩大到 CEval 指定 task。
```

## 场景 5：对齐历史 12ms 配置复现

```text
请复现历史上 <model_name> TPOT 约 <historical_tpot_ms> ms 的配置，并与当前代码对比。

需要对齐：
- 代码 commit / branch
- 模型权重和 draft 权重
- TP / devices / block_size / max_memory_utilization
- chunked prefill / graph / schedule overlap / MTP 开关
- top_p / top_k / temperature / max_tokens / max-prompt-length
- evalscope warmup-num、parallel、number

输出：
1. 历史配置是否能在当前环境复现。
2. 不能复现时，逐项说明差异和可能影响。
3. 当前代码在完全对齐配置下的 TTFT/TPOT/TPS。
4. 若性能差异仍存在，给出下一步 profiling 对比计划。
```
