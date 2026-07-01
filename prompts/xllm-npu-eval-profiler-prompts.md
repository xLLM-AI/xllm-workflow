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
请使用 xllm-npu-perf-runner 执行 evalscope 性能评测。
若服务未启动，请先使用 xllm-npu-server-manager 启动服务。

配置：
- API URL：<api_url>
- 模型名：<model_name>
- tokenizer：<tokenizer_path>
- TP=<tp>（用于服务启动配置，若服务已运行则忽略）
- parallel=<parallel_list，如 1,2,4>（并发数列表，逐个测试）
- number=<number，每个并发场景的请求数，如 4>
- artifact root：<run_root>

要求：
1. 确认 evalscope 已安装（evalscope + evalscope[perf]）。
2. 更新 scripts/eval_perf.sh 中的 model、url、tokenizer-path，并按用户指定的 parallel 列表和 number 生成对应的 evalscope perf 命令块。
3. warmup-num 必须大于 0，除非明确是在测冷启动。
4. 结果输出到 $RUN_ROOT/perf/，保留 evalscope 原始目录，提取 benchmark_summary.json 同步到 metrics.json。
5. 输出 TTFT、TPOT、TPS、吞吐、P50/P90/P99。
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

## 场景 8：多模型批量性能评测（不同尺寸、不同 TP）

> 对多个模型循环执行场景 2，每个模型独立拉起服务、测试、停止。
> 使用 `xllm-npu-batch-perf` skill，支持简写约定，自动推导路径和设备。

### 示例 A：极简写法（推荐）

```text
请使用 xllm-npu-batch-perf 批量评测以下模型：

模型：
1. Qwen3.5-27B：2卡
2. Qwen3.5-35B-A3B：2卡
3. Qwen3.6-27B：2卡
4. Qwen3.5-4B：单卡，不开MTP

环境：
- SSH：103
- xllm容器：cann9-xllm-wh
- evalscope容器：cann8.5-xllm-wh
- xllm binary：/export/home/weinan5/wanghao/xllm-cann9/build/xllm/core/server/xllm
- 权重目录：/export/home/models/
- MTP导出工具：/export/home/weinan5/wanghao/xllm-cann9/tools/export_mtp.py
- 参考脚本：/export/home/weinan5/wanghao/vllm_vs010.sh
- 端口：18039

测试：input=2048, output=2048, parallel=1,2,4
```

### 示例 B：带自定义参数

```text
请使用 xllm-npu-batch-perf 批量评测：

模型：
1. Qwen3.5-27B：2卡，parallel=1,2,4,8
2. DeepSeek-V3：8卡，input=4096, output=512

环境：
- SSH：103
- xllm容器：cann9-xllm-wh
- xllm binary：/export/home/weinan5/wanghao/xllm-cann9/build/xllm/core/server/xllm
- 权重目录：/export/home/models/
- MTP投机步数：5
- 端口：18039

公共：warmup=2, number=4, max_memory_utilization=0.8
```

### 示例 C：同一模型多轮复测

```text
请使用 xllm-npu-batch-perf，对 Qwen3.5-27B 执行 3 轮复测验证稳定性。

配置：2卡，MTP，input=2048, output=2048, parallel=1,2,4

环境：
- SSH：103
- xllm容器：cann9-xllm-wh
- xllm binary：/export/home/weinan5/wanghao/xllm-cann9/build/xllm/core/server/xllm
- 权重目录：/export/home/models/
- 端口：18039

要求：每轮重启服务，计算均值和标准差，偏离>10%标记异常。
```

### 简写约定说明

Agent 会自动按以下规则补全：

| 用户写法 | 自动推导 |
|---|---|
| `Qwen3.5-27B：2卡` | `model_path=/export/home/models/Qwen3.5-27B`<br>`devices=0,1`<br>`MTP=开启`（默认） |
| `Qwen3.5-4B：单卡，不开MTP` | `model_path=/export/home/models/Qwen3.5-4B`<br>`devices=0`<br>`MTP=关闭` |
| 省略 `draft_model_path` | 自动设为 `<model_path>-mtp` |
| 省略 `tokenizer_path` | 自动设为 `<model_path>` |
| 指定 `参考脚本` | 自动提取启动参数作为默认值 |
| 指定 `MTP导出工具` | draft 目录不存在时自动调用生成 |
