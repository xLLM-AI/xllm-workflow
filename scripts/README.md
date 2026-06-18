# scripts/ — 确定性引擎

编译、启动服务、性能测试、精度测试等自动化脚本库。
这些脚本是**确定性**的——LLM 不得修改脚本逻辑，变更需人工审核。

## 内容

- `query.py` — 查询 `reference/pr_history/` 中的模型 dossier（按模型、关键词、路径过滤）
- `init_xllm_workspace.py` — 初始化 `code/xllm`，从 `config.example.json` 生成本地 `config.json`，读取或补齐 xLLM 仓库信息，并按启动方式链接 skills
- `start_xllm_service.py` — 从 `config.json` 和 CLI 参数启动 xLLM NPU 服务，自动找空闲卡、避让端口并解析启动日志摘要
- `collect_evalscope_results.py` — 收集并标准化 evalscope 评测结果
- `compare_npu_benchmark.py` — 跨框架 NPU 性能对比
- `validate_framework_cli.py` — 验证框架 CLI 参数合法性

## 原则

- 本目录脚本为跨 skill 共用工具；skill 专属脚本保留在各 skill 的 `scripts/` 子目录
- 所有脚本必须能在仓库根目录下直接运行
- 参数变更写入本地 `config.json`，不在脚本中硬编码；共享默认值写入 `config.example.json`

## 初始化 xLLM 代码仓和 Skills

方式 1：在本项目根目录启动 code agent。脚本会初始化 `code/xllm`，并把本项目
`skills/*` 与 xLLM 仓内 skills 链接到生成目录 `.agents/skills`：

```bash
python scripts/init_xllm_workspace.py
```

方式 2：在 `code/xllm` 下启动 code agent。脚本会初始化 `code/xllm`，并把本项目
`skills/*` 链接到所选 agent 的 skills 目录：

```bash
python scripts/init_xllm_workspace.py --mode xllm --agent codex
# 或兼容快捷参数
python scripts/init_xllm_workspace.py --install-project-skills --agent codex
```

如果 `config.json` 不存在，脚本会先从 `config.example.json` 生成本地文件。如果本地 `config.json` 中还没有 xLLM 仓库配置，脚本会交互式询问仓库 URL、分支或 commit，并写回：

```json
{
  "code": {
    "xllm": {
      "path": "code/xllm",
      "origin": {
        "url": "<your-fork-or-origin-url>",
        "branch": "<branch>",
        "commit": ""
      },
      "upstream": {
        "url": "https://github.com/jd-opensource/xllm.git",
        "branch": "main",
        "commit": ""
      }
    }
  }
}
```

非交互场景可直接传参：

```bash
python scripts/init_xllm_workspace.py \
  --repo-url <git-url> \
  --ref <branch-or-commit> \
  --ref-type branch
```

脚本只会在 `code/xllm` 不存在或为空时拉取代码；如果目录已存在，会跳过 clone。

## 启动 xLLM NPU 服务

`start_xllm_service.py` 用于在当前工作区启动 xLLM OpenAI-compatible
服务。脚本会读取本地 `config.json`，自动寻找空闲 NPU 逻辑卡，端口被占用时自动向后
寻找可用端口，并在服务 ready 后从 `node_*.log` 中提取 KV Cache、blocks、可存 token
数和显存摘要。

基本用法：

```bash
python scripts/start_xllm_service.py
```

常用覆盖参数：

```bash
python scripts/start_xllm_service.py \
  --model /models/Qwen3-8B \
  --tp-size 2 \
  --start-port 18000 \
  --master-node-addr 127.0.0.1:9748
```

指定 xLLM binary：

```bash
python scripts/start_xllm_service.py \
  --xllm-bin code/xllm/build/lib.linux-aarch64-cpython-311/xllm/xllm
```

只检查配置、选卡和启动命令，不真正启动：

```bash
python scripts/start_xllm_service.py --dry-run --once
```

非交互模式下缺失必填配置直接失败，适合自动化脚本：

```bash
python scripts/start_xllm_service.py --non-interactive
```

### 配置优先级

启动配置按以下顺序生效：

1. CLI 参数
2. `config.json`
3. `config.example.json` 模板默认值
4. 脚本内仅用于运行控制的默认值

`config.json` 中已经存在的字段不会在脚本里重复定义默认常量。当前支持覆盖的
config 字段包括：

- `code.xllm.path`
- `code.xllm.origin.url`
- `code.xllm.origin.branch`
- `code.xllm.origin.commit`
- `code.xllm.upstream.url`
- `code.xllm.upstream.branch`
- `code.xllm.upstream.commit`
- `xllm_config.model`
- `xllm_config.model_id`
- `xllm_config.max_memory_utilization`
- `xllm_config.max_seqs_per_batch`
- `xllm_config.max_tokens_per_chunk_for_prefill`
- `xllm_config.max_tokens_per_batch`
- `xllm_config.tp_size`
- `xllm_config.draft_model`
- `xllm_config.num_speculative_tokens`

对应 CLI 参数为：

```text
--xllm-code-path
--xllm-origin-url / --xllm-origin-branch / --xllm-origin-commit
--xllm-upstream-url / --xllm-upstream-branch / --xllm-upstream-commit
--model
--model-id
--max-memory-utilization
--max-seqs-per-batch
--max-tokens-per-chunk-for-prefill
--max-tokens-per-batch
--tp-size
--draft-model
--num-speculative-tokens
```

CLI 覆盖只影响本次运行，不写回 `config.json`。只有两类情况会写回
`config.json`：本地配置缺少模板字段时补齐 schema；`xllm_config.model` 为空且用户在
交互提示中输入模型路径时补齐必填值。

### 运行参数

以下参数不写入 `config.json`，由脚本默认值控制，也可以用 CLI 覆盖：

```text
--xllm-bin
--host
--start-port
--master-node-addr
--hccl-if-base-port
--log-dir
--communication-backend
--npu-kernel-backend
--block-size
--enable-prefix-cache / --disable-prefix-cache
--enable-chunked-prefill / --disable-chunked-prefill
--enable-schedule-overlap / --disable-schedule-overlap
--enable-shm / --disable-shm
--poll-interval-seconds
--ready-timeout-seconds
--free-hbm-usage-pct-max
--free-aicore-usage-pct-max
--extra-xllm-arg
```

`--npu-kernel-backend` 对应 xLLM 原生 `--npu_kernel_backend`，支持 `AUTO`、`ATB`
和 `TORCH`。脚本默认值是 `AUTO`，但当模型路径或 `model_id` 看起来是 Qwen3 且用户
没有显式指定该参数时，脚本会使用 `TORCH`，以避开当前环境中 Qwen3 AUTO 解析到 ATB
后可能长时间停在权重加载阶段的问题。如需验证 ATB 路径，可显式传
`--npu-kernel-backend ATB`。

Qwen3 快速启动示例：

```bash
python scripts/start_xllm_service.py \
  --model /models/Qwen3-1.7B \
  --model-id Qwen3-1.7B
```

`--extra-xllm-arg` 用于透传脚本尚未建模的 xLLM 原生参数，可重复使用。例如：

```bash
python scripts/start_xllm_service.py \
  --model /models/Qwen3-1.7B \
  --extra-xllm-arg=--some_future_xllm_flag=value
```

如果没有传 `--xllm-bin`，脚本会根据最终生效的 `code.xllm.path` 依次查找常见构建产物：

```text
<code.xllm.path>/build/lib.*/xllm/xllm
<code.xllm.path>/build/xllm/core/server/xllm
<code.xllm.path>/build/bin/xllm
<code.xllm.path>/xllm
PATH 中的 xllm
```

### 启动进度日志

脚本启动时会持续输出带时间戳的进度日志，并用带分割线的对齐块展示关键摘要，
包括：

- 当前读取的 `config.json`
- 生效的模型路径、xLLM binary、xLLM 代码路径和主要 batch 配置
- 空闲卡扫描条件、最终选择的 NPU 逻辑卡和 `ASCEND_RT_VISIBLE_DEVICES`
- API 端口、master 端口、HCCL 基础端口和实际 endpoint
- 生效的 NPU kernel backend
- dry-run、ready、启动成功和启动失败摘要
- 每个 rank 的 PID、`start_command_rank_<rank>.txt` 和 `node_<rank>.log`
- 每个 rank 的完整启动命令块，命令块上下带分割线，`exec xllm` 参数按多行展示，
  内容与 `start_command_rank_<rank>.txt` 一致
- 等待 `/v1/models` ready 的周期性进度、启动日志最后一行和日志多久没有更新

如果等待 ready 时间较长，直接根据输出中的 `Startup log:` 路径查看启动日志：

```bash
tail -f runs/xllm_start/<timestamp>/service/node_0.log
```

如果等待超时或启动过程中按 `Ctrl-C`，脚本会清理本次启动出来但尚未 ready 的
xLLM 进程；只有服务 ready 后才会保留后台进程。

### 空闲卡与端口

脚本使用 `npu-smi info -m` 的 `Chip Logic ID` 作为最终设备 ID。默认空闲卡判定：

- 该逻辑卡无进程
- HBM usage 不高于 `--free-hbm-usage-pct-max`
- AICore usage 不高于 `--free-aicore-usage-pct-max`

空闲卡不足 `xllm_config.tp_size` 时，脚本会按 `--poll-interval-seconds` 轮询等待。
传入 `--once` 时只检查一次，不等待。

脚本会检查 API 端口区间 `start_port ... start_port + tp_size - 1` 和
`master_node_addr` 中的端口。若端口被占用，会自动向后寻找可用端口，并在启动摘要中
打印请求端口和实际端口。本次端口避让不会写回 `config.json`。

### 日志与启动摘要

日志默认写入：

```text
runs/xllm_start/<timestamp>/service/
```

目录内包含：

- `node_<rank>.log` — 每个 rank 的 xLLM 启动日志
- `start_command_rank_<rank>.txt` — 每个 rank 的实际启动命令
- `pids.txt` — rank、PID 和日志路径

启动成功后，脚本会输出：

- Endpoint、模型、xLLM binary、TP、选中的 NPU 逻辑卡、实际端口和日志目录
- 每个 rank 的 total memory、available memory、KV Cache、blocks、block size
- `blocks * block_size` 计算出的可存 token 数
- `total memory - available memory` 估算的每卡权重和非 KV 占用

如果日志中还没有相关字段，摘要会提示未解析到，直接查看对应 `node_<rank>.log`。
