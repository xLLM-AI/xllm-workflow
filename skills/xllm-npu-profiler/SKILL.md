---
name: xllm-npu-profiler
description: 昇腾 NPU 910B3 (A3) 上的 xLLM 推理 Profiling 分析。提供五表报告（kernel/重叠/融合/下发效率/内存效率），支持 xLLM 和 vLLM-Ascend 对比分析，Prefill/Decode 阶段分离。当用户需要定位 NPU 推理性能瓶颈时使用。
---

# xLLM NPU Profiling 分析

## 概述

在华为昇腾 NPU 910B3 (A3) 上进行推理 Profiling 分析，输出五表报告。

工作流入口：
- [scripts/run_profiling.sh](scripts/run_profiling.sh) — xLLM dynamic profiling 采集
- [scripts/multibatch_test.py](scripts/multibatch_test.py) — profiling 采集 workload 生成
- [scripts/analyze_xllm_npu_profile.py](scripts/analyze_xllm_npu_profile.py) — 已导出 PROF 数据解析
- [scripts/render_triage_npu.py](scripts/render_triage_npu.py) — 五表 Markdown 渲染

正式 profiling 产物必须遵循
[`../../reference/io_specs/profiling-artifact-schema.md`](../../reference/io_specs/profiling-artifact-schema.md)；
run 元信息遵循
[`../../reference/io_specs/run-manifest-template.md`](../../reference/io_specs/run-manifest-template.md)。
Profiling run 用于解释瓶颈，不直接替代无 profiling 的 before/after 性能数据。

当 profiling 结论涉及 decode-step gap、graph replay gap、host bubble、pipeline
边界或 xLLM/vLLM-Ascend pipeline 差异时，必须联动
[`xllm-npu-pipeline-analysis`](../xllm-npu-pipeline-analysis/SKILL.md)，并在对应
profiling run 目录生成它要求的 pipeline artifact。最低要求是
`manifest.md`、`timeline_notes.md`、`pipeline-analysis.md`、`bubble-table.csv`、
`stage-table.csv`、`rank-skew-table.csv` 和 `analysis.json`；缺失时不得把该
profiling 作为正式 hostbound 结论。

## 能力矩阵

| 能力 | xLLM | vLLM-Ascend |
|------|------|-------------|
| 已有 trace 分析 | yes | yes |
| 实时采集 | yes（`PROFILING_MODE=dynamic` + msprof attach） | yes（profiler 配置） |
| 阶段分离采集 | yes（Prefill/Decode 独立） | 有限 |
| 昇腾 msprof 采集 | yes | yes |
| 两阶段 trace 对比 | yes（eager/graph-on） | yes |

## 五表输出契约

`triage` 输出固定五张表，每张表仅渲染累计 Device/AICore 时间占比 ≥ 1.0% 的行。

| 表名 | 内容 | 数据来源 |
|------|------|---------|
| **Kernel Table** | AICore/AI CPU 内核按 Device 时间占比排序 | `op_statistic*.csv` / `op_summary*.csv` |
| **Communication / Overlap-Opportunity Table** | 通信热点与计算-通信重叠机会 | `communication_statistic*.csv` + `task_time*.csv` |
| **Fuse-Pattern Table** | 融合算子模式匹配 | 模型代码 + torch_npu 映射（确定性，非模糊匹配） |
| **下发效率表** | Hostbound 分析：stream task 密度/间隔/等待 | `task_time*.csv` + `analysis.db` / `msprof_*.db` |
| **内存效率表** | xTensor/KV Cache 利用率与碎片 | xLLM metric + profiling 数据 |

## 使用场景

- 分析 xLLM 或 vLLM-Ascend 的昇腾 Profiling trace
- 实时采集运行中服务的 Profiling 数据
- 总结 Prefill/Decode 阶段哪些 kernel 族主导性能
- 判断代码路径是否仍有重叠/融合机会
- 检查已知优化路径是否被正确启用

## 主要工作流

### 1. 已有 trace 分析

```bash
python scripts/analyze_xllm_npu_profile.py \
  --input /path/to/profiling_results/ \
  --framework xllm
```

输入目录应包含昇腾 Profiling 标准输出：
- `op_statistic*.csv`
- `op_summary*.csv`
- `task_time*.csv`
- `communication_statistic*.csv`
- `analysis.db` 或 `msprof_*.db`

脚本可以直接接收 `PROF_*` 根目录，也可以接收其中的
`mindstudio_profiler_output/` 子目录。MindStudio/msprof 自动生成的时间戳文件名会被
自动识别，例如 `op_statistic_20260523203844.csv`。

### 2. xLLM 实时采集（当前推荐）

当前推荐使用 Ascend `msprof --dynamic=on` attach 到已启动的 xLLM 父进程，
并通过 FIFO 控制采集窗口。该方式能把 warmup 和正式采集分开，避免把模型加载、
ACL graph warmup、首轮编译等噪声混入 trace。

前置要求：
- profiling 脚本不负责启动 xLLM。先用正常启动脚本启动服务并完成 healthcheck，
  再 attach profiling；如果本次 profiling 临时启动了服务，结束前要明确是否保留
  或停止服务，避免 HBM/PID 残留污染后续性能测试。
- xLLM 启动脚本中必须设置：
  ```bash
  export PROFILING_MODE=dynamic
  ```
- 采集脚本传入的 PID 必须是 xLLM 父进程 PID，可通过 `ps -ef | grep xllm`
  查找；不要使用 `npu-smi info` 中看到的 device worker PID。
- 采集端口、模型名、tokenizer 路径必须与 xLLM 服务启动配置一致。

脚本契约：
- 若使用本 skill 的 `scripts/run_profiling.sh` + `scripts/multibatch_test.py`
  组合采集，必须先在 xLLM 启动脚本中加入 `export PROFILING_MODE=dynamic`，
  再启动服务。
- `PROFILING_MODE=dynamic` 属于服务启动侧配置；`run_profiling.sh` 只负责
  `msprof --dynamic=on --pid` attach、warmup、写入 `start/stop` 控制采集窗口、
  以及 `msprof --export=on` 导出结果。
- 如果启动脚本未设置 `PROFILING_MODE=dynamic`，后续即使 `msprof` attach 成功，
  也可能无法得到预期的动态采集窗口或完整 profiling 数据。
- 若未生成 `PROF_*`、未导出 `mindstudio_profiler_output/`、workload 命令失败、
  或 warmup/healthcheck 被混入正式采集窗口，该次 profiling 只能标为
  `INCONCLUSIVE`，不能支撑优化结论。

典型采集流程：

```bash
# 1. 启动 xLLM 服务前开启 dynamic profiling mode
export PROFILING_MODE=dynamic
xllm ... --port 38050 ...

# 2. 找到 xLLM 父进程 PID
ps -ef | grep xllm

# 3. 使用 msprof dynamic attach 采集
scripts/run_profiling.sh <xllm_parent_pid> ./xllm_profile full
```

`run_profiling.sh` 的核心采集方式：

```bash
msprof \
  --dynamic=on \
  --output="$OUTPUT_DIR" \
  --model-execution=on \
  --runtime-api=on \
  --aicpu=on \
  --pid="$XLLM_PID" < "$PIPE_FILE" &

echo "start" >&3
python3 multibatch_test.py ...
echo "stop" >&3
msprof --export=on --output="$LATEST_PROF"
```

推荐参数语义：
- `mode=full`：先 warmup，再打开 profiling 采正式请求。
- `mode=warmup`：只预热，不采集。
- `mode=test`：只采正式请求，适合服务已预热后的补采。
- `BATCH_SIZE`：每批并发请求数，用于模拟并发用户。
- `NUM_BATCHES`：正式采集批次数。
- `WARMUP_BATCHES`：不采集 profiling 的预热批次数。
- `INPUT_TOKENS` / `OUTPUT_TOKENS`：用 tokenizer 生成接近目标 token 数的请求。

采集完成后分析导出的 `mindstudio_profiler_output/`：

```bash
python scripts/analyze_xllm_npu_profile.py \
  --input /path/to/xllm_profile_YYYYMMDD_HHMMSS/PROF_xxx \
  --framework xllm
```

### 3. vLLM-Ascend 实时采集

vLLM-Ascend 侧可用其 profiler 配置生成 trace；本 skill 的分析脚本仍只消费
已经导出的 profiling 目录。

```bash
VLLM_WORKER_MULTIPROC_METHOD=spawn vllm serve /path/to/model \
  --tensor-parallel-size 4 \
  --profiler-config '{"profiler":"torch","torch_profiler_dir":"/tmp/vllm-profile"}'

python scripts/analyze_xllm_npu_profile.py \
  --input /tmp/vllm-profile/PROF_xxx \
  --framework vllm-ascend \
  --output /tmp/vllm-profile-analysis.json
```

### 4. 两阶段 trace 分析（eager/graph-on 对比）

```bash
python scripts/analyze_xllm_npu_profile.py \
  --input /path/to/eager_profile/PROF_xxx \
  --framework xllm \
  --output /tmp/eager-profile-analysis.json

python scripts/analyze_xllm_npu_profile.py \
  --input /path/to/graph_on_profile/PROF_xxx \
  --framework xllm \
  --output /tmp/graph-profile-analysis.json
```

mapping trace 用于恢复 `kernel → cpu_op → python scope` 映射。
formal trace 用于实际性能分析。

### 5. 阶段分离采集

`analyze_xllm_npu_profile.py` 只分析已经导出的 `PROF_*` 目录，不负责发送请求
或启动采集。Prefill/Decode 阶段分离时，使用 `run_profiling.sh` 改不同 workload
参数后分别采集，再分别离线分析。

```bash
# Prefill-focused: 长输入、短输出
INPUT_TOKENS=4090 OUTPUT_TOKENS=1 \
  scripts/run_profiling.sh <xllm_parent_pid> /tmp/xllm-prefill full

python scripts/analyze_xllm_npu_profile.py \
  --input /tmp/xllm-prefill_YYYYMMDD_HHMMSS/PROF_xxx \
  --framework xllm \
  --output /tmp/xllm-prefill-analysis.json

# Decode-focused: 短输入、长输出
INPUT_TOKENS=1 OUTPUT_TOKENS=2048 \
  scripts/run_profiling.sh <xllm_parent_pid> /tmp/xllm-decode full

python scripts/analyze_xllm_npu_profile.py \
  --input /tmp/xllm-decode_YYYYMMDD_HHMMSS/PROF_xxx \
  --framework xllm \
  --output /tmp/xllm-decode-analysis.json
```

与 SOTA loop 联动时必须使用慢场景的实际 input/output 长度。

## 全局瓶颈判定

```
空闲率 >20%  → Hostbound（算子下发/GE编译/H2D传输瓶颈）
计算率 >85%  → Computing（热点 kernel 优化空间）
通信率 >10%  → Communication（AllReduce/AllGather 瓶颈）
内存碎片高   → Memory（xTensor/KV Cache 碎片）
```

判定后分发到子分析：
- **Hostbound**：图模式覆盖率、GE/AclGraph 编译开销、算子下发效率、H2D/D2H 拷贝
- **Computing**：Top-N 热点算子、MatMul/GEMM 形状分析、融合机会（torch_npu）
- **Communication**：AllReduce/AllGather 带宽、TP 通信开销、通信-计算重叠率
- **Memory**：KV Cache 碎片率、xTensor 池命中率、Block 分配策略

## 工作流

### 单 trace 分析

1. 如果用户仅需诊断，一个 trace 足够
2. 优先使用单 rank trace 而非合并 trace
3. 对于实时采集，确认框架的 Profiling 前置条件已满足
4. 优先手工分离 Prefill/Decode workload 采集，二者瓶颈差异显著
5. 采集前清空目标目录

### 两 trace 分析

1. 先采集 mapping trace（graph 关闭 / 低融合配置）
2. 再采集 formal trace（实际服务优化配置）
3. 运行 `triage` 生成五表报告
4. 按此顺序阅读结果：
   - Kernel Table → Overlap-Opportunity Table → Fuse-Pattern Table → 下发效率表 → 内存效率表
5. 在声称"新优化机会"前，对照：
   - [references/npu-fuse-catalog.md](references/npu-fuse-catalog.md) — 已知融合模式
   - [references/npu-overlap-catalog.md](references/npu-overlap-catalog.md) — 已知重叠机会
6. 优先报告：
   - 本应生效的已有融合/重叠路径
   - 本应生效但疑似禁用/不支持/回归的路径
   - 其他框架已有但本地缺失的上游模式
   - 仅当没有 catalog 条目匹配时，才报告真正的"新机会"

### 昇腾 Profiling 数据格式

详见 [references/ascend-profiling-formats.md](references/ascend-profiling-formats.md)。

关键文件：
- `op_statistic*.csv`：算子调用统计，优先用于 Kernel Table
- `op_summary*.csv`：AICore/AI Vector 详细算子统计，作为 fallback
- `task_time*.csv`：task timeline，用于 stream 下发效率
- `communication_statistic*.csv`：HCCL 通信统计
- `analysis.db`：SQLite 格式详细分析数据

## 渲染五表 Markdown

```bash
python scripts/render_triage_npu.py \
  --analysis-root /path/to/analysis_root \
  --output /path/to/analysis_bundle.md
```

输出将按模型分组，保留每个框架的五表。

## 参考资料

按需加载：
- [../../reference/knowledge/profiler-source-map.md](../../reference/knowledge/profiler-source-map.md) — xLLM profiler 入口和 trace 写入路径
- [references/npu-fuse-catalog.md](references/npu-fuse-catalog.md) — NPU 融合算子目录
- [references/npu-overlap-catalog.md](references/npu-overlap-catalog.md) — NPU 重叠机会目录
- [../../reference/knowledge/ascend-profiling-formats.md](../../reference/knowledge/ascend-profiling-formats.md) — 昇腾 Profiling 数据格式
- [references/qwen35-27b-kernel-profile.md](references/qwen35-27b-kernel-profile.md) — Qwen3.5-27B Baseline vs MTP kernel profiling 对比分析

## MTP 相关性能检查要点

当分析 MTP (Multi-Token Prediction) 相关 profiling trace 时，额外检查：

| 检查维度 | 健康值 | 异常信号 |
|---------|-------|---------|
| MTP 启用证据 | rank 日志同时有 `draft_model_path`、`Using draft devices`、`Speculative decode is enabled` | 只有 `--num_speculative_tokens` 或 evalscope accept rate |
| draft 权重 | 已导出独立 `*-mtp` 目录 | 直接拿主模型目录当 draft |
| `--num_speculative_tokens` | 依 workload 扫描 | 只看 accept rate 选择更大 nst |
| Spec Accept Rate | 使用服务端 `/vars` delta 判断 | 只有 evalscope 推导值 |
| Decoded Tok/Iter | 不明显超过 `nst + 1` | 明显超过上限且没有 chunk 聚合解释 |
| Memory | reserved linear cache 和 KV blocks 有余量 | MTP 深度导致容量明显下降 |

MTP 历史 profiling 复盘、transpose 消除、小算子反例和 draft-prepare overlap
经验放在
[`references/mtp-profiling-lessons.md`](references/mtp-profiling-lessons.md)。
只有当前任务涉及 MTP/speculative decode 时再加载。

## 输出契约

返回：
- trace 路径或生成的 profiling 路径
- 框架（xLLM / vLLM-Ascend）
- 模型/服务器参数
- 五表报告（kernel/overlap/fuse/下发/内存）
- 可选相似性标注（high/medium/low）
- Prefill/Decode 各阶段的主要瓶颈总结
- 重叠证据来源说明（单 trace / 两 trace）
