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

> 本场景提供结构化参数模板。完整的执行流程（含 full/incremental 模式切换、evalscope 容器调度、启动前清理、报告生成等操作步骤）以 `skills/xllm-npu-benchmark/references/benchmark-prompt-template.md` 为准。两者冲突时，以 benchmark-prompt-template 为准。

```text
请使用 xllm-npu-benchmark 和 xllm-npu-eval-runner，在宿主机调度两个命名容器，
对比 xLLM 与 vLLM-Ascend 的 <model_name> 性能。

=== 前置条件 ===
- SSH 连接：<ssh_host>（使用 SSH key 认证，不要在 prompt 中写密码）
- 宿主机工作目录：<work_dir>
- 容器状态：<已启动 | 需要启动>
- 若需启动，xLLM 启动脚本：<xllm_server_script>
- 若需启动，vLLM-Ascend 启动脚本：<vllm_server_script>

=== 容器配置 ===
- xLLM 容器名：<xllm_container>
- xLLM 镜像 tag/digest：<xllm_image>
- xLLM 版本/commit：<xllm_version>
- vLLM-Ascend 容器名：<vllm_container>
- vLLM-Ascend 镜像 tag/digest：<vllm_image>
- vLLM-Ascend 版本：<vllm_version>

=== 服务配置 ===
- xLLM 服务端口：<xllm_port>
- vLLM-Ascend 服务端口：<vllm_port>
- API 路径：/v1/chat/completions

=== NPU 配置 ===
- 物理 NPU 型号：<npu_model，如 Ascend 910B3>
- xLLM 可见卡：<xllm_visible_devices，如 0,1>
- vLLM-Ascend 可见卡：<vllm_visible_devices，如 2,3>
- TP=<tp_size>

=== 模型配置 ===
- 模型权重：<model_path>
- tokenizer：<tokenizer_path>
- dtype：<dtype，如 bfloat16>

=== evalscope 配置 ===
- evalscope 运行位置：<宿主机 | 统一 client 容器>
- evalscope 版本：<evalscope_version>
- dataset=random
- input_tokens=<input_tokens，如 2048>
- output_tokens=<output_tokens，如 2048>
- parallel=<parallel>
- number=<number，smoke 用 4，正式建议 >= 100>
- warmup-num=<warmup_num，>= 2>
- temperature=0.0
- top_p=<top_p>
- top_k=<top_k>
- ignore_eos=true

=== 输出配置 ===
- artifact root：<run_root，建议格式：runs/<日期>_<模型>_<对比类型>>

=== 要求 ===
1. 不要在 xLLM 容器里安装或启动 vLLM-Ascend；宿主机负责 docker exec 调度。
2. 正式 benchmark 使用命名长驻容器，不默认使用 docker run --rm。
3. 两边使用同一模型权重、同一 tokenizer、同一物理 NPU 型号/卡数/可见卡顺序。
4. 每个框架 run 前后保存宿主机 npu-smi、进程表、CPU/memory/load 快照。
5. 保存容器名、镜像 tag/digest、框架 commit 或 package 版本、启动命令、端口和日志。
6. evalscope 优先在宿主机或统一 client 容器运行；若在服务容器内运行，记录 evalscope 版本。
7. 输出 TTFT、TPOT、TPS、Output throughput、P50/P90/P99，并说明结果是否可作为正式结论。
8. 若任一框架服务未就绪或环境异常，先报告问题，不要跳过检查直接跑 benchmark。
```
