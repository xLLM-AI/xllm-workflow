# xLLM NPU 评测与 Profiling 中文 Prompts

## 场景 1：启动服务并做 smoke 请求

```text
请使用 xllm-npu-eval-runner，按 <server_script> 启动 xLLM 服务并做 smoke 验证。

输入：
- xLLM 仓库：<xllm_repo>
- 启动脚本：<server_script>
- 请求脚本或 curl body：<request_script_or_json>
- 模型：<model_name>
- 端口：<port>
- artifact root：<run_root>

要求：
1. 启动前记录 git status、commit、submodule 状态、NPU 状态和关键环境变量。
2. 如果服务已运行，先确认是否是目标 commit 和目标模型。
3. 请求返回后保存 response、server log、healthcheck 和 manifest。
4. smoke 只证明服务可用，不作为性能或精度正式结论。
```

## 场景 2：evalscope 性能评测，必须带 warmup

```text
请使用 xllm-npu-eval-runner 执行 evalscope 性能评测。

配置：
- URL：<api_url>/v1/chat/completions
- tokenizer：<tokenizer_path>
- 模型名：<model_name>
- dataset：<random | line_by_line | custom>
- 输入/输出：<input_tokens>/<output_tokens>
- parallel=<parallel>
- number=<number>
- warmup-num=<warmup_num>
- temperature=<temperature>
- top_p=<top_p>
- top_k=<top_k>
- ignore_eos=<true_or_false>
- outputs-dir：<run_root>/perf/<run_id>

要求：
1. warmup-num 必须大于 0，除非明确是在测冷启动。
2. 保存 evalscope 原始输出、metrics.json、report.md 和 manifest。
3. 输出 TTFT、TPOT、TPS、吞吐、P50/P90/P99。
4. 标记本次结果是否可用于正式性能结论。
```

## 场景 3：CEval 指定分类精度评测

```text
请使用 xllm-npu-eval-runner 和 xllm-npu-accuracy-debug，评测 CEval 指定分类。

配置：
- 分类：<task_list，例如 operating_system,computer_architecture>
- 题数范围：<all | first_N>
- 模型：<model_name>
- API URL：<api_url>
- temperature=0
- top_p=<top_p>
- top_k=<top_k>
- max_tokens=<max_tokens>
- artifact root：<run_root>/accuracy/<run_id>

要求：
1. 保存每题 prompt、prediction、answer、是否正确。
2. 输出每个 task 的题数和分数，不要只给总分。
3. 若出现乱码或异常答案，抽取 failed_cases.jsonl。
4. 若是 PR 回归验证，必须在 good/current/fixed 三个版本上跑同一批题。
```

## 场景 4：采集 xLLM dynamic profiling

```text
请使用 xllm-npu-profiler 采集 xLLM dynamic profiling。

前提：
- 服务已启动，PID=<xllm_parent_pid>
- 启动脚本已设置 export PROFILING_MODE=dynamic
- workload 与正式性能场景一致：输入 <input_tokens>，输出 <output_tokens>，parallel=<parallel>
- warmup 批数：<warmup_batches>
- profiling 输出：<profiling_output_dir>

要求：
1. profiling 脚本只 attach 已启动服务，不隐式启动 xLLM。
2. 保存 PROF_*、mindstudio_profiler_output、workload log、capture log、manifest。
3. profiling 用于解释瓶颈，不能直接与非 profiling 性能数据比较。
4. 采集后运行 analyzer，输出五表报告：kernel、通信/重叠、融合、dispatch、memory。
```

## 场景 5：容量/OOM 与 KV cache 分析

```text
请使用 xllm-npu-capacity-planner 分析 <model_name> 的容量或 OOM 问题。

输入：
- 启动日志：<server_log>
- 模型 config：<model_config_path>
- TP/PP/EP：<parallel_config>
- block_size=<block_size>
- max_memory_utilization=<value>
- max_model_len=<value>
- MTP/draft 配置：<mtp_config_or_none>

输出：
1. HBM 分桶表：权重、runtime workspace、KV cache、MTP reserve、free margin。
2. KV block 数量、理论 token 容量、最大并发估算。
3. OOM 或启动失败的最可能原因。
4. 可调参数建议及风险：block_size、max_memory_utilization、max_model_len、MTP reserve。
```

## 场景 6：基线与优化后 Profiling 对比

```text
请使用 xllm-npu-profiler 对比 baseline 和 optimized 两份 profiling。

输入：
- baseline profiling：<baseline_profile_dir>
- optimized profiling：<optimized_profile_dir>
- baseline perf：<baseline_perf_dir>
- optimized perf：<optimized_perf_dir>

要求：
1. 先确认两次 workload、warmup、采样参数和服务配置一致。
2. 输出五表差异：热点 kernel、hostbound gap、copy/fill、同步、HCCL、memory。
3. 说明优化代码是否命中了预期 timeline 事件。
4. 如果 TPOT 没有收益，判断是优化未生效、被新瓶颈抵消，还是评测噪声。
```

## 场景 7：xLLM 与 vLLM-Ascend 容器隔离 A/B 性能对比

> 完整执行流程（含 full/incremental 模式、容器调度、启动前清理、报告生成等）
> 以 `skills/xllm-npu-benchmark/references/benchmark-prompt-template.md` 为准。
> 本场景仅提供快速参数清单。

```text
请使用 xllm-npu-benchmark，按 benchmark-prompt-template.md 执行 A/B 对比。

需填写参数：
- 运行模式：<full | incremental>
- SSH：<ssh_host>
- 容器：<xllm_container> / <vllm_container>
- 端口：<xllm_port> / <vllm_port>
- 启动脚本：<xllm_start_script> / <vllm_start_script>
- evalscope 容器：<evalscope_container>
- 模型权重：<model_path>，tokenizer：<tokenizer_path>
- TP=<tp>
- input_tokens=<input_tokens>，output_tokens=<output_tokens>
- parallel=<parallel_list>
- artifact root：<artifact_root>
- vLLM 历史结果路径（仅 incremental）：<vllm_history_path>
```
