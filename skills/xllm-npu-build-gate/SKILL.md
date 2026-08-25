---
name: xllm-npu-build-gate
description: xLLM、vLLM-Ascend、SGLang NPU 可执行构建门禁。识别 checkout/worktree、校验框架适配的构建身份、submodule、工具链和必需 patch，执行显式命令，并生成可追溯 binary verdict。
---

# xLLM NPU 可执行构建门禁

本 skill 是 benchmark 的强制前置层。它主动检查环境、选择构建策略、执行构建并保存
provenance；无法证明源码、build tree 和 binary 一致时返回 `BLOCKED`，不继续测评。

## 职责边界

| 阶段 | 责任方 |
|---|---|
| 环境预检、构建计划、构建执行、binary verdict | 本 skill |
| build-gate 返回 `FAILED` 后的根因诊断 | `xllm-npu-incident-triage` |
| 只消费 `PASS` binary，执行服务/精度/性能测评 | `xllm-npu-eval-runner` |

`xllm-npu-eval-runner` 不再手工修补构建环境，也不得消费 `BLOCKED`/`FAILED` 产物。

## 可执行入口

```bash
python <skill_dir>/scripts/build_gate.py \
  --framework xllm \
  --repo <xllm_checkout_or_worktree> \
  --run-root <run_root> \
  --build-dir <cmake_build_dir> \
  --binary <xllm_binary> \
  --base-ref origin/main \
  --opp-marker <installed_vendor>/.xllm_ops_git_head \
  --opp-package-root <cpack_staging>/packages/vendors/custom_xllm_math \
  --execute \
  --configure-command '<full configure/build command>' \
  --incremental-command '<incremental xllm target command>' \
  --tilelang-command '<affected TileLang family command>'
```

`--framework` 支持 `xllm`（默认）、`vllm-ascend` 和 `sglang`。非 xLLM 适配器使用
`--targeted-command` 处理内核/扩展变化；未显式提供 `--build-dir` 时不强制要求 CMake
cache，也不执行 `xllm_ops` 检查。xLLM 保留原有 CMake、TileLang 和 `xllm_ops` 强门禁。

脚本按计划自动选择三个命令之一；命令必须显式提供，避免猜测不同 xLLM checkout 的
构建入口。若 `xllm_ops` source HEAD 与 OPP marker 不一致，还必须提供：

```bash
--xllm-ops-command '<rebuild and reinstall OPP command>'
```

退出码与 verdict 一致：

| 退出码 | verdict | 含义 |
|---|---|---|
| `0` | `PASS` | 构建成功，binary 和 xllm_ops OPP payload 均通过一致性验证 |
| `1` | `FAILED` | 构建命令失败或 binary 验证失败 |
| `2` | `BLOCKED` | 环境/patch/submodule/命令不完整，不能安全构建 |

不加 `--execute` 只生成计划并返回 `BLOCKED`，不能作为 benchmark 前置 PASS。

## 自动预检

脚本必须检查并记录：

- bare repo、普通 checkout、linked worktree 类型及真实 repo root。
- branch、commit、dirty status/diff SHA、untracked file SHA。
- recursive submodule commit；未初始化、冲突或状态不可读直接 `BLOCKED`。
- `CMakeCache.txt` 的 source root、Python executable、架构、compiler、Torch_DIR。
- 当前 Python headers、`torch`/`torch_npu`、libtorch ABI 和 ATB header。
- 正式 eval 前加 `--require-npu`，检查 `npu-smi` 和 `/dev/davinci*` 等设备节点；
  相关进程快照写入 `environment.json`。
- `third_party/xllm_ops` HEAD 与 `.xllm_ops_git_head` OPP marker；构建后必须重新读取，
  不得复用 preflight 快照。
- CPack staging 与实际安装 OPP 中 `op_impl`、`op_proto`、`op_api` 的文件集合及 SHA256；
  缺文件、多文件或内容不同均返回 `FAILED`。
- 对每个 AscendC 动态算子校验单算子 config、`binary_info_config.json`、kernel JSON 和
  `.o` 的闭包关系；算子未进入聚合索引、索引路径不一致或产物缺失均返回 `FAILED`。
- xllm_ops 构建和主构建共享同一把主机级 OPP 文件锁，防止不同 worktree 并发覆盖全局 vendor。
- 每个 `--required-patch` 的 SHA256，以及是否已应用到候选源码。
- 最终 binary 的路径、SHA256、大小、`file` 和 `ldd -r`。

`--skip-toolchain-checks` 仅供无 NPU 的离线测试使用，不得用于正式 build verdict。
`--require-npu` 用于即将进入 eval 的 gate；只做离线编译时可不启用。

## 构建策略

| 检测结果 | 自动计划 |
|---|---|
| build tree 缺失、CMake source/Python/架构不匹配、configure 输入或 submodule commit 变化 | `reconfigure` |
| CMake identity 一致，仅普通源码变化 | `incremental` |
| TileLang kernel/wrapper 变化且 configure identity 一致 | `tilelang-targeted` |
| vLLM-Ascend/SGLang kernel 或 extension 变化 | `framework-targeted` |
| `xllm_ops` HEAD 与 OPP marker 不一致 | 在主构建前追加 `rebuild_and_install_xllm_ops` |
| 构建后 marker 未刷新或 OPP payload 与 CPack staging 不一致 | `FAILED`，禁止消费 binary |
| 动态 kernel 已编译但 config 未在最后重新生成，或聚合索引缺失该算子 | `FAILED`，禁止启动服务 |
| submodule 未初始化/冲突、必需 patch 缺失、工具链不可证明 | `BLOCKED` |

### Fresh worktree / rebase

linked worktree 会写入计划理由。若 build tree 不存在、submodule commit 改变或 configure
identity 不一致，必须选择 `reconfigure`，不能直接复用旧增量产物。heavy rebase 后应把
目标 base 通过 `--base-ref` 传入，使 configure/third_party 变化进入 fingerprint。

### TileLang 默认策略

- `--tilelang-start-method` 默认 `spawn`。
- `--tilelang-worker-cap` 默认 `16`。
- TileLang 实际并发取 `min(--jobs, --tilelang-worker-cap)`；不会把大机器 CPU 数直接当 worker 数。
- 构建命令可读取 `BUILD_GATE_START_METHOD` 和 `BUILD_GATE_TILELANG_WORKERS`。
- `build-plan.json` 记录变更路径、worker cap 和 start method；build 输出实时写入
  `build.log`。
- `--no-output-timeout` 默认 `900` 秒；超时会 TERM/KILL 当前构建、记录最后一行
  family/variant 进度并返回 `FAILED`，不得无限等待。
- 构建命令在继承当前环境的非 login Bash 中执行。CANN、Python 等工具链环境必须在
  调用 build gate 前加载；不要依赖主机 login profile 在构建期间隐式修改环境。

### 测试并发变量

执行环境统一设置 `CTEST_PARALLEL`，并记录但忽略 `CTEST_PARALLEL_LEVEL`。同时设置
`MAX_JOBS` 和 `CMAKE_BUILD_PARALLEL_LEVEL`，实际值写入 `environment.json`。

### 本机必需 patch

例如权重加载修复必须作为候选身份显式传入：

```bash
--required-patch /path/to/weight-loading-fix.patch
```

patch 不存在或未应用时返回 `BLOCKED`；脚本不会静默修改候选源码。

## 确定性产物

每次调用都会在 `$RUN_ROOT/build/` 写出：

```text
environment.json
build-plan.json
submodules.txt
source-fingerprint.json
build.log
binary-provenance.json
verdict.json
```

详细字段见
[`references/build-gate-artifacts.md`](references/build-gate-artifacts.md)。即使 repo 类型错误等
早期失败，也必须生成完整文件集合；未到达的阶段写入 `unavailable` 原因。

## Agent 执行流程

1. 从用户配置、xLLM 仓库构建文档或已验证脚本取得三类 build command；不自行猜测。
2. 把本机必需 patch、OPP marker、build dir 和 binary 路径显式传给脚本。
   若 CPack staging 不在 `third_party/xllm_ops` 下，必须通过 `--opp-package-root` 显式传入。
3. 执行 gate，读取 `verdict.json`，不要只看命令退出文本。
4. `PASS`：把 `binary-provenance.json` 和 binary 路径交给 eval-runner。
5. `BLOCKED`：补齐环境或命令后重跑，禁止 benchmark。
6. `FAILED`：连同 `build.log` 和 artifacts 委托 incident-triage 做根因诊断。

多候选复用、候选环境变量和权重加载验证要求见
[`references/build-gate-operations.md`](references/build-gate-operations.md)。

## 脚本

- `scripts/build_gate.py`：确定性 preflight、build-plan、执行与 provenance gate。
