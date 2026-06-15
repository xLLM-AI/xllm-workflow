# Benchmark Prompt 模板

提供 full 和 incremental 两种模式的完整 prompt 模板，
用户只需修改变量即可使用。

> 本模板是执行 A/B 对比 benchmark 的权威操作指南。`prompts/xllm-npu-eval-profiler-prompts.md` 场景 7 提供简化的参数模板，两者冲突时以本文件为准。

## 变量说明

| 变量 | 说明 | 示例 |
|------|------|------|
| 运行模式 | full / incremental | full |
| 模型权重 | 模型路径 | /export/home/models/Qwen3.5-27B |
| TP | 张量并行度 | 2 |
| 并发数 | parallel 列表 | 1, 2, 4 |
| artifact root | 产物根目录 | /export/home/weinan5/wanghao/runs/20260610_mtp |
| vLLM 历史结果路径 | 仅 incremental 模式 | /export/home/weinan5/wanghao/runs/20260610_parallel_{parallel}/vllm-ascend/perf/ |
| xllm 容器 | xLLM 容器名 | cann9-xllm-wh |
| vllm 容器 | vLLM 容器名 | vllm-018rc1-wh |
| evalscope 容器 | evalscope 执行容器名 | cann8.5-xllm-wh |
| xllm 端口 | xLLM 服务端口 | 18035 |
| vllm 端口 | vLLM 服务端口 | 18037 |

## 完整 Prompt

```
请使用 xllm-npu-benchmark 和 xllm-npu-eval-runner，在宿主机调度两个命名容器，
使用evalscope对比 xLLM 与 vLLM-Ascend 的 Qwen3.5-27B 性能。

运行模式：full
（可选值：full = 全量对比，两个框架都重新跑；incremental = 增量对比，仅重跑 xLLM，vLLM 使用历史结果）

宿主机服务器连接方式：ssh <ssh_host>（使用 SSH key 认证，参考 xllm-npu-eval-runner 的 ssh-exec-constraints.md）
xllm执行路径：<xllm_workdir>
xllm启动脚本：<xllm_start_script>
vllm-ascend启动脚本：<vllm_start_script>
evalscope启动脚本示例：<evalscope_script>
evalscope执行容器：<evalscope_container>

固定配置：
- xllm容器：<xllm_container>
- vllm-ascend容器：<vllm_container>
- vLLM-Ascend 版本：<vllm_version>
- 模型权重：<model_path>
- tokenizer：<tokenizer_path>
- TP=<tp>
- dataset=random
- input_tokens=<input_tokens>
- output_tokens=<output_tokens>
- parallel=<parallel_list> （分别测试并发）
- number=4*parallel
- warmup-num=4
- temperature=0.0
- ignore_eos=true
- artifact root：<artifact_root>/parallel_{parallel}
- vLLM历史结果路径（仅 incremental 模式使用）：<vllm_history_path>

要求：
1. 不要在 xLLM 容器里安装或启动 vLLM-Ascend；宿主机负责 docker exec 调度。
2. 正式 benchmark 使用命名长驻容器，不默认使用 docker run --rm。
3. 两边使用同一模型权重、同一 tokenizer、同样的npu数量。
4. 启动脚本检查：
   - full 模式：检查 xllm 和 vllm-ascend 的启动脚本一致性（功能性配置须保持一致）
   - incremental 模式：只检查 xllm 启动脚本，确认新场景参数已正确配置
5. 启动前清理与 NPU 检查：
   - full 模式：在容器内执行 pkill -9 vllm 和 pkill -9 xllm，确保无环境冲突或进程残留
   - incremental 模式：在 xllm 容器内执行 pkill -9 xllm，确保无环境冲突或进程残留
   - 两种模式均需检查 npu 空闲情况，选择空闲的 npu 拉起服务
6. 每个框架 run 前后保存宿主机 npu-smi、进程表、CPU/memory/load 快照。
7. 保存容器名、镜像 tag/digest、框架 commit 或 package 版本、启动命令、端口和日志。
8. 端口配置：
   - full 模式：vllm-ascend 和 xllm 启动时指定不同的端口号
   - incremental 模式：只指定 xllm 端口号，vLLM 不启动
9. evalscope 在指定容器运行，通过端口号区分不同服务。evalscope已经在指定容器中安装好了，无需重新安装。
10. 执行evalscope前使用curl -v http://127.0.0.1:{PORT}/v1/models命令确认模型名称。
11. 输出 TTFT、TPOT、TPS、Output throughput 的 avg、P50、P90、P99 指标，并说明结果是否可作为正式结论。
12. 操作文件时在evalscope容器中以root权限操作。
13. 在容器中进行任何操作时，均以root用户进行。
14. 测试执行流程：
    - full 模式：
      a. 启动 xLLM 服务，执行 evalscope（所有 parallel）
      b. 停止 xLLM 服务
      c. 启动 vLLM-Ascend 服务，执行 evalscope（所有 parallel）
      d. 停止 vLLM-Ascend 服务
      e. 对比两个框架的结果
    - incremental 模式：
      a. 启动 xLLM 服务，执行 evalscope（所有 parallel）
      b. 停止 xLLM 服务
      c. 从 vLLM历史结果路径 读取已有的 evalscope 输出
      d. 将 xLLM 新结果与 vLLM 历史结果进行对比分析
      e. vLLM 容器不需要启动，不需要执行任何操作
15. 对性能结果进行对比分析并生成报告，存放进artifact root目录下。
16. 报告要求：
    - 报告必须使用中文撰写
    - full 模式：报告中说明两个框架均为本次新跑结果
    - incremental 模式：报告中明确标注 xLLM 为本次新跑结果，vLLM-Ascend 为历史基线结果（引用 vLLM历史结果路径）
    - 为每个并发场景分别生成独立的对比报告
    - 生成一份总报告，汇总所有并发场景的完整对比分析（包含所有指标的avg、p50、p90、p99）
    - 总报告和各并发报告均存放进对应的artifact root目录
17. SSH命令执行约束：遵守 xllm-npu-eval-runner 的 `references/ssh-exec-constraints.md` 中的引号规范和认证方式。
```

## 使用示例

### 全量对比

```
运行模式：full
artifact root：/export/home/weinan5/wanghao/runs/20260610_bench
```

### 增量对比

```
运行模式：incremental
artifact root：/export/home/weinan5/wanghao/runs/20260610_mtp
vLLM历史结果路径：/export/home/weinan5/wanghao/runs/20260610_parallel_{parallel}/vllm-ascend/perf/
```
