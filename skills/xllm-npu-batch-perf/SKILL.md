---
name: xllm-npu-batch-perf
description: xLLM NPU 批量性能评测编排器。对多个模型（不同尺寸、不同 TP 配置）循环执行"启动服务 → evalscope 性能测试 → 停止服务"流程，自动收集所有结果。
---

# xLLM NPU 批量性能评测编排器

对多个模型循环执行场景 2（evalscope 性能评测），每个模型独立拉起服务、测试、停止。
内部复用 `xllm-npu-server-manager` 和 `xllm-npu-perf-runner` 两个子 skill。

## 核心约束

### 参考脚本关键配置不可变

当用户提供了 `reference_script`（参考启动脚本）时，Agent 必须从中提取以下参数并**原样使用**，
不得自行修改、优化或"调参"：

| 锁定参数 | 说明 |
|---|---|
| `max_memory_utilization` | 显存利用率上限 |
| `max_tokens_per_batch` | 每 batch 最大 token 数 |
| `max_seqs_per_batch` | 每 batch 最大序列数 |
| `block_size` | KV cache block 大小 |
| `communication_backend` | 通信后端 |
| `max_concurrent_requests` | 最大并发请求数 |
| `enable_graph` | 图模式开关 |
| `enable_prefix_cache` | prefix cache 开关 |
| `enable_chunked_prefill` | chunked prefill 开关 |
| `enable_schedule_overlap` | schedule overlap 开关 |
| `enable_shm` | 共享内存开关 |

**唯一例外**：用户在 prompt 中**显式指定**了某个参数的值，此时以用户指定的值为准。
Agent 不得以"性能更好"、"避免 OOM"等理由自行调整这些参数。

### 启动前检查空卡

启动服务前必须通过 `npu-smi info` 检查 NPU 设备状态，**只使用无进程占用的空闲卡**：

1. 解析 `npu-smi info` 输出中的进程列表（Process section），识别被占用的 NPU 编号。
2. 从空闲卡中选取所需数量的连续设备。
3. 如果空闲卡不足，向用户报告并中止，不得强行使用被占用的卡。
4. 不要硬编码设备编号（如固定用 `0,1`），必须动态检测。

### 单卡启动失败自动升级 TP

如果模型配置为单卡（TP=1）但服务启动失败（常见原因：HCCL 初始化错误、OOM），
自动升级为 TP=2 重试一次。重试时从空闲卡中选取 2 张。

## 子 Skill 依赖

| 职责 | 使用 |
|---|---|
| 服务生命周期管理 | `xllm-npu-server-manager` |
| 性能测试执行 | `xllm-npu-perf-runner` |
| 报告生成 | `xllm-npu-report-writer`（模板：`references/summary-template.md`） |

## 简写约定

Agent 收到用户的简写 prompt 时，按以下约定自动补全为完整 batch config：

### 模型路径推导

| 规则 | 示例 |
|---|---|
| `model_path` = `model_dir` + `model_name` | `model_dir=/export/home/models/`, `model_name=Qwen3.5-27B` → `/export/home/models/Qwen3.5-27B` |
| `tokenizer_path` = `model_path` | 同上 |
| `draft_model_path` = `model_path` + `-mtp` | `/export/home/models/Qwen3.5-27B-mtp` |

### MTP 默认行为

- **MTP 默认开启**。用户不写 MTP 相关字段时，视为开启 MTP。
- 只有用户明确写 `no_mtp`、`不开MTP`、`无MTP` 等否定表述时，才禁用 MTP。
- `num_speculative_tokens` 从 common 配置继承（默认 `3`）。
- 如果 draft model 目录不存在，且 common 中配置了 `mtp_export_tool`，自动调用该脚本生成 MTP 权重。

### 设备分配

- **不要硬编码设备编号**。启动前通过 `npu-smi info` 动态检测空闲卡。
- 从空闲卡中选取所需数量：TP=2 → 选 2 张空闲卡，TP=4 → 选 4 张空闲卡。
- 被占用的卡（有进程运行）必须跳过。
- 用户只需写 `TP=N` 或 `N卡`，不需要写设备列表。

### 模型列表简写格式

用户可以用一行描述一个模型，格式：

```
<model_name>：<tp描述>[，<mtp描述>]
```

其中：
- `<tp描述>`：`单卡` / `TP1` / `2卡` / `TP=2` / `TP4` 等
- `<mtp描述>`：省略=开启MTP / `MTP` =开启 / `不开MTP` / `no_mtp` =禁用

示例：

| 用户写法 | 解析结果 |
|---|---|
| `Qwen3.5-27B：2卡，MTP` | nnodes=2, devices=0,1, MTP on |
| `Qwen3.5-35B-A3B：TP=2` | nnodes=2, devices=0,1, MTP on（默认） |
| `Qwen3.5-4B：单卡，不开MTP` | nnodes=1, devices=0, MTP off |
| `DeepSeek-V3：8卡` | nnodes=8, devices=0-7, MTP on（默认） |

### 基础设施信息

如果用户提供了 SSH、容器等信息，归入 batch config 的 `infra` 字段。
所有命令通过 `ssh` + `docker exec` 在远程容器中执行：

- `xllm_container`：运行 xLLM 服务的容器
- `evalscope_container`：运行 evalscope 的容器（可选，不提供则在 xllm_container 中执行）
- 遵守 [`ssh-remote-exec`](../ssh-remote-exec/SKILL.md) skill 的 SSH 执行约束

### 参考启动脚本

如果用户指定了 `reference_script`，Agent 应先读取该脚本，提取其中的启动参数
（如 `max_memory_utilization`、`block_size`、`communication_backend` 等）作为 common 默认值。

**关键约束**：参考脚本中的以下参数视为"锁定"，Agent 不得自行修改：
`max_memory_utilization`、`max_tokens_per_batch`、`max_seqs_per_batch`、`block_size`、
`communication_backend`、`max_concurrent_requests`、`enable_graph`、`enable_prefix_cache`、
`enable_chunked_prefill`、`enable_schedule_overlap`、`enable_shm`。

用户在 prompt 中显式指定的参数优先级高于脚本中的值。

## 批量配置格式

完整 JSON 格式（Agent 从用户简写 prompt 自动生成）：

```json
{
  "batch_name": "multi_model_perf_20260622",
  "infra": {
    "ssh_host": "",
    "xllm_container": "",
    "evalscope_container": "",
    "reference_script": "",
    "mtp_export_tool": ""
  },
  "common": {
    "xllm_bin": "",
    "start_port": 17112,
    "model_dir": "/export/home/models/",
    "parallel_list": "1,2,4",
    "number": 4,
    "warmup_num": 2,
    "input_tokens": 2048,
    "output_tokens": 2048,
    "num_speculative_tokens": 3,
    "max_memory_utilization": 0.75,
    "block_size": 128,
    "communication_backend": "lccl",
    "enable_prefix_cache": true,
    "enable_chunked_prefill": true,
    "enable_schedule_overlap": true,
    "enable_graph": true,
    "enable_shm": true
  },
  "models": [
    {
      "model_name": "Qwen3.5-27B",
      "nnodes": 2,
      "mtp": true,
      "parallel_list": "1,2,4"
    },
    {
      "model_name": "Qwen3.5-4B",
      "nnodes": 1,
      "mtp": false
    }
  ]
}
```

### 字段说明

**infra**（基础设施，全部可选）：

| 字段 | 说明 | 默认 |
|---|---|---|
| `ssh_host` | SSH 远程主机（如 `103`） | 空=本地执行 |
| `xllm_container` | xLLM 服务容器名 | 空=宿主机执行 |
| `evalscope_container` | evalscope 容器名 | 空=在 xllm_container 中执行 |
| `reference_script` | 参考启动脚本路径，提取默认参数 | 空 |
| `mtp_export_tool` | MTP 权重导出脚本路径 | 空 |

**common**（全局默认值，各 model 可覆盖）：

| 字段 | 说明 | 默认值 |
|---|---|---|
| `xllm_bin` | xllm binary 路径 | 自动检测 |
| `start_port` | 起始端口 | `17112` |
| `model_dir` | 模型权重根目录 | `/models/` |
| `parallel_list` | 并发数列表（逗号分隔） | `"1"` |
| `number` | 每个并发级别的请求数基数 | `4` |
| `warmup_num` | warmup 请求数 | `2` |
| `input_tokens` | 输入 token 长度 | `2048` |
| `output_tokens` | 输出 token 长度 | `2048` |
| `num_speculative_tokens` | MTP 投机步数 | `3` |

**models[]**（每个模型最简只需 3 个字段）：

| 字段 | 说明 | 必填 |
|---|---|---|
| `model_name` | 模型标识（用于拼接路径） | 是 |
| `nnodes` | TP 数（即卡数） | 是 |
| `mtp` | 是否启用 MTP | 否（默认 `true`） |
| `parallel_list` | 覆盖全局并发列表 | 否 |
| `input_tokens` | 覆盖全局输入长度 | 否 |
| `output_tokens` | 覆盖全局输出长度 | 否 |

**自动推导字段**（不需要用户填写）：

| 字段 | 推导规则 |
|---|---|
| `model_path` | `model_dir` + `model_name` |
| `tokenizer_path` | = `model_path` |
| `draft_model_path` | `model_path` + `-mtp`（仅当 `mtp=true`） |
| `visible_devices` | 启动前通过 `npu-smi info` 动态检测空闲卡，选取 nnodes 张 |
| `num_speculative_tokens` | 继承 common 值（仅当 `mtp=true`） |

## 编排流程

```
1. 参数对齐：从用户简写 prompt 生成 batch config JSON
       |
2. 创建 Batch Run Root：runs/batch/<timestamp>_<batch_name>/
       |
3. （可选）读取 reference_script，提取启动参数补充 common（锁定参数不可变）
       |
3.5 检查空闲 NPU 卡（npu-smi info），动态分配设备
       |
4. 循环每个 model：
   ├── 4a. 停止已有服务（pkill -9 xllm）
   ├── 4b. 创建 model run root：$BATCH_ROOT/<model_name>/
   ├── 4c. 自动推导 model_path、draft_model_path，从空闲卡分配 visible_devices
   ├── 4c-fallback. 单卡启动失败时自动升级 TP=2 重试
   ├── 4d. 若 mtp=true 且 draft 目录不存在，调用 mtp_export_tool 生成
   ├── 4e. 设置环境变量 → 调用 xllm-npu-server-manager 启动服务
   ├── 4f. 等待服务 Ready（轮询 /models endpoint）
   ├── 4g. 设置环境变量 → 调用 xllm-npu-perf-runner 执行性能测试
   ├── 4h. 收集结果到 $MODEL_ROOT/perf/
   └── 4i. 停止服务
       |
5. 汇总所有模型结果 → $BATCH_ROOT/summary.md
```

### Step 1: 参数对齐

1. 解析用户的简写 prompt，按「简写约定」自动补全。
2. 生成完整 batch config JSON，保存到 `$BATCH_ROOT/batch_config.json`。
3. 缺失的必要参数一次性询问用户。

### Step 2: 创建 Batch Run Root

```bash
BATCH_ROOT="runs/batch/$(date +%Y%m%d_%H%M%S)_${BATCH_NAME}"
mkdir -p "$BATCH_ROOT"
```

### Step 3: 读取参考脚本（可选）

如果 `infra.reference_script` 非空，读取该脚本内容，提取以下参数作为 common 默认值：
- `max_memory_utilization`、`block_size`、`communication_backend`
- `max_tokens_per_batch`、`max_seqs_per_batch`、`max_concurrent_requests`
- `enable_prefix_cache`、`enable_chunked_prefill`、`enable_graph` 等

**关键约束**：以上参数从参考脚本原样提取后锁定，Agent 不得自行修改。
用户在 prompt 中显式指定的参数优先级高于脚本提取值。

### Step 4: 循环每个模型

#### 4a. 停止已有服务

```bash
pkill -9 xllm || true
sleep 5
```

如果配置了 `infra`，通过 SSH + docker exec 执行：

```bash
ssh <ssh_host> "docker exec <xllm_container> bash -c 'pkill -9 xllm || true'"
sleep 5
```

#### 4b. 创建 Model Run Root

```bash
MODEL_ROOT="$BATCH_ROOT/$MODEL_NAME"
mkdir -p "$MODEL_ROOT"/{env,perf,service}
```

#### 4c. 自动推导路径和设备

```
model_path = model_dir + model_name
tokenizer_path = model_path
draft_model_path = model_path + "-mtp"  (仅 mtp=true)
```

**设备分配**：不要硬编码 `0,1,...,nnodes-1`。启动前通过 `npu-smi info` 检查进程列表，
识别被占用的 NPU 卡，从空闲卡中选取所需数量。如果空闲卡不足，向用户报告并中止。

#### 4c-fallback. 单卡启动失败自动升级 TP

如果模型配置为 TP=1 但服务启动失败（常见：HCCL get root info failed、OOM），
自动升级为 TP=2 重试一次，从空闲卡中选取 2 张。

#### 4d. MTP 权重自动导出

如果 `mtp=true` 且 `draft_model_path` 目录不存在：

```bash
python3 <mtp_export_tool> --model <model_path> --output <draft_model_path>
```

如果 `mtp_export_tool` 为空，向用户报告缺少 MTP 权重并跳过该模型。

#### 4e-4i. 启动、测试、收集、停止

同之前流程，通过环境变量调用 `xllm-npu-server-manager` 和 `xllm-npu-perf-runner`。
如果配置了 `infra`，所有命令通过 `ssh <ssh_host> "docker exec <container> bash -c '...'"` 执行。

### Step 5: 汇总报告

委托 `xllm-npu-report-writer` 生成报告，传入本 skill 的模板：

```
加载 xllm-npu-report-writer，参数：
  Run Root: $BATCH_ROOT
  template_path: skills/xllm-npu-batch-perf/references/summary-template.md
  report_type: batch-perf
```

report-writer 将按 `references/summary-template.md` 的结构生成 `$BATCH_ROOT/summary.md`，包含：

1. **环境信息**：Date、Batch、Host、Container、Devices、Port。
2. **配置表**：列出本次评测的所有关键参数（从 reference_script 和 common 配置提取）。
3. **性能对比表**：每个模型在每个 parallel 下的 TTFT (ms)、TPOT (ms)、Output tok/s、Total tok/s、Spec Accept Rate。
   - 表格格式：`| Model | TP | MTP | Parallel | TTFT (ms) | TPOT (ms) | Output tok/s | Total tok/s | Spec Accept |`
   - 同一模型的多行并发用空单元格（`| | | |`）表示，只在第一行填写 Model/TP/MTP。
   - 数值保留 1 位小数（TTFT/TPOT）或 1 位小数（tok/s）。
   - Spec Accept Rate 以百分比显示（如 66.9%），无 MTP 的模型填 `-`。
4. **Key Findings**：总结最优模型、关键对比结论、并发退化幅度等。
5. **Notes**：记录异常情况（启动失败自动升级 TP、MTP 自动导出等）。

## 脚本

- **单模型执行**：`scripts/run_single_model.sh` — 封装单个模型的"启动 → 测试 → 停止"流程

## 故障处理

- **某个模型启动失败**：记录错误到 `$MODEL_ROOT/error.log`，跳过该模型继续执行下一个。
- **单卡启动失败**：如果模型配置为 TP=1 但启动失败（HCCL 错误、OOM 等），自动升级为 TP=2 重试一次。
- **MTP 权重缺失**：尝试自动导出，导出失败则跳过并记录。
- **性能测试超时**：设置单轮超时（默认 30 分钟），超时后停止并记录。
- **NPU 资源不足**：启动前检查 `npu-smi info`，如果可用显存不足则跳过并告警。
- **空闲卡不足**：启动前检测空闲 NPU 卡数量，如果不足以满足模型 TP 需求，向用户报告并中止。
