---
name: xllm-npu-build-gate
description: xLLM NPU 构建验证与门禁。用于编译、构建、build gate、PR rebase 后构建验证、fresh worktree 构建准备、多候选分支复用 build tree、NPU 设备门禁检查。本 skill 是测评前置验证层，不负责测评执行、服务启动或性能对比。
---

# xLLM NPU 构建验证与门禁

本 skill 负责 xLLM 在 NPU 环境下的构建验证和设备门禁，是测评流程的前置条件层。
涵盖三个核心能力：

1. **NPU 门禁**：确认设备可用、驱动正常、无进程占用
2. **多候选构建复用**：对比多个 PR/分支时复用 build tree，避免重复全量编译
3. **CMake 增量重编**：在已有 build tree 上只重编变更部分，加速候选切换

本 skill 不负责测评执行（交给 `xllm-npu-eval-runner`）、服务启动（交给 `xllm-npu-server-manager`）或编译失败诊断（交给 `xllm-npu-incident-triage`）。

## 职责边界

| 需求 | 使用 |
|---|---|
| NPU 设备门禁检查 | 本 skill |
| 编译、构建、build gate | 本 skill |
| PR rebase 后构建验证 | 本 skill |
| 多候选分支复用 build tree | 本 skill |
| CMake 增量重编 | 本 skill |
| 编译失败、链接失败、submodule 缺失 | `xllm-npu-incident-triage` |
| 测评执行（性能/精度） | `xllm-npu-eval-runner` |
| 服务启动/停止 | `xllm-npu-server-manager` |

## NPU 门禁

正式启动服务前必须先做轻量 NPU gate，并把结果写入 `$RUN_ROOT/env/`：

### 检查项

- `npu-smi info` 能成功返回
- 预期的 `/dev/davinci*`、`/dev/davinci_manager`、`/dev/devmm_svm`、`/dev/hisi_hdc`
  在当前执行环境可见
- `python3 -c "import torch; import torch_npu"` 不超时
- 没有无关 xLLM/evalscope/msprof 进程占用目标 NPU

### 门禁失败处理

如果 `npu-smi` 报 `dcmi module initialize failed`、设备节点不可见，或
`torch_npu` import 超时，不要产出正式性能结论。先把 gate 标记为 failed，
保留日志，并等待机器或容器 NPU 映射恢复后再继续。

### 检查脚本

```bash
# NPU 设备可见性
npu-smi info > "$RUN_ROOT/env/npu-smi.before.txt" 2>&1

# 设备节点检查
ls /dev/davinci* /dev/davinci_manager /dev/devmm_svm /dev/hisi_hdc \
  > "$RUN_ROOT/env/device_nodes.txt" 2>&1

# torch_npu 可用性（超时 30 秒）
timeout 30 python3 -c "import torch; import torch_npu; print('OK')" \
  > "$RUN_ROOT/env/torch_npu_gate.txt" 2>&1

# 进程占用检查
pgrep -af 'xllm|vllm|sglang|python|evalscope|msprof' \
  > "$RUN_ROOT/env/process.before.txt" 2>&1 || true
```

## 多候选 xLLM 分支构建复用

如果同一任务需要比较 baseline、多个 PR 或多个候选分支，优先使用一个固定
eval lane 和一个 build tree，避免每个候选都全量 `python setup.py build`。

### 推荐模式

1. 在任务目录下创建单独 worktree，例如 `$TASK_ROOT/eval-lane`。
2. 每个候选都基于同一个 main/base commit 生成分支，并应用本机必需 patch。
3. 先完成一次可复用 CMake configure/build，再通过 `git checkout <candidate>`
   和 `cmake --build <build-dir> --target xllm` 做增量重编。
4. 如果 `python setup.py build` 会触发 TileLang 或自定义算子长时间编译，
   使用已有构建文档中的手工 CMake 路径，并把所有绕过步骤记录到 manifest。
5. 每次候选切换后记录 branch、commit、dirty status、build log、binary `file`
   输出和 `ldd` 是否存在 `not found`。

### 环境变量 Gating

候选 PR 如果通过环境变量启用优化路径，不能只应用代码 diff 就跑 benchmark。
切换候选后先从 diff 中扫描 `std::getenv` / `getenv` / `XLLM_ENABLE_` /
`XLLM_SKIP_` gate；启动脚本必须显式导出候选所需变量，并在 service log
和 manifest 中打印 `env | sort | grep -E '^XLLM_(ENABLE|SKIP)_'`。如果没有
这份 env 证据，该候选的性能只能标记为配置不完整的 debug run，不能和其他 PR
做正式胜负结论。

### 权重加载验证

如果本机 patch 是为绕过权重 mmap 或 safetensors 映射问题，验证点必须覆盖
模型加载阶段，而不只是推理请求成功。优先在 `StateDict` 读取 safetensors 后立刻
materialize/clone 到 CPU owned tensor；不要把 clone 延迟到 `load_weight()` 的
多线程加载阶段，否则可能把 mmap 生命周期和并发权重加载混在一起，表现为加载卡住
或极慢。必要时临时降低 `HFModelLoader.load_weights` 并发，并在服务日志中记录每个
shard 的 `Loaded model weights` 与最终 `Weight loading completed`。

### 多候选 Sequence Wrapper

多候选任务建议提供一个 task-local sequence wrapper，而不是让用户手动串命令。
wrapper 应按固定顺序执行：

```text
checkout candidate branch
-> incremental rebuild
-> NPU gate
-> launch service
-> wait ready
-> accuracy smoke
-> warmed-up perf without profiling
-> dynamic profiling and five-table render
-> stop service
```

注意 official perf 和 profiling 必须分开跑：前者用于性能比较，后者只用于解释瓶颈。
如果 gate 失败，wrapper 应在启动服务前停止，并保留 gate artifact。

## CMake 增量重编

增量 CMake 重编不是裸 `cmake --build`。`python setup.py build --device npu`
会先调用 `set_npu_envs()`，设置 PyTorch、torch_npu、Ascend、ATB、TileLang 等
编译和链接环境；直接复用 build tree 时必须显式复用这些环境，否则最终链接可能缺
Torch wheel 的伴随动态库，例如
`torch.libs/libgfortran-e1b7dfc8.so.5.0.0`，表现为
`libopenblasp-*.so: undefined reference to _gfortran_*`。

### 最低环境要求

在本机直接增量编 `xllm` 时，最低要确认：

```bash
export LD_LIBRARY_PATH="$(python3 - <<'PY'
import os, torch
root = os.path.dirname(os.path.abspath(torch.__file__))
paths = [root + ".libs", root, os.path.join(root, "lib")]
print(":".join(p for p in paths if os.path.isdir(p)))
PY
):${LD_LIBRARY_PATH:-}"
source /usr/local/Ascend/ascend-toolkit/set_env.sh
source /usr/local/Ascend/nnal/atb/set_env.sh
cmake --build build/cmake.linux-aarch64-cpython-311 --target xllm -j64
```

### Build Tree 选择

如果 `setup.py` 的 build tree 是刚生成的，优先使用它配置好的
`build/cmake.<platform>-<python>` 目录；如果手工 CMake 仍然失败，不要把
`libgfortran`、`torch.libs`、ATB 或 Ascend runtime 的链接错误当作代码回归，
先补齐环境并在 manifest 中记录实际 `LD_LIBRARY_PATH`、`CMakeCache.txt` 和失败的
link line。

### 常见环境问题

候选切换触发 CMake reconfigure 时，注意两个常见本机环境问题：

- 顶层 CMake 可能在 configure 阶段预编译 `third_party/xllm_ops`。如果已安装
  OPP marker `.xllm_ops_git_head` 与 `git -C third_party/xllm_ops rev-parse HEAD`
  一致，可以导出
  `XLLM_OPS_GIT_HEAD_CACHED=$(git -C third_party/xllm_ops rev-parse HEAD)`，
  跳过不必要的预编译。若 marker 不匹配，不要强行跳过。
- source 官方 ATB 环境后，要验证 `$ATB_HOME_PATH/include/atb/atb_infer.h`
  存在。若 host env 指到错误 ABI 目录，应覆盖到真实安装目录后再 configure/build，
  并在 manifest 中记录。

## 故障处理

- **NPU 门禁失败**：保留日志到 `$RUN_ROOT/env/`，不产出正式结论，等待环境恢复。
- **增量编译链接失败**：检查 `LD_LIBRARY_PATH`、`CMakeCache.txt`，记录失败的 link line。
- **环境变量缺失**：扫描候选 diff 中的 `getenv` 调用，显式导出所需变量。
- **编译失败诊断**：交给 `xllm-npu-incident-triage`。
