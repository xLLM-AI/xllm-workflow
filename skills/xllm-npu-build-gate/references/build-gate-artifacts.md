# Build Gate Artifact Contract

所有 JSON 文件使用 `schema_version: 1`。消费者必须先读取 `verdict.json`，只有
`status=PASS` 且 `binary_ready=true` 才能启动 benchmark。

## `environment.json`

- repo 类型：checkout、linked worktree、git/common dir。
- host platform、architecture、CPU 数。
- Python、torch/torch_npu、headers、ATB 检查结果。
- 可选 NPU gate 的 `npu-smi`、设备节点和相关进程快照。
- OPP lock 路径、对应 marker parent 和等待时长。
- 选定的非敏感构建环境和并发变量。
- 门禁不设置或记录 CTest 环境变量，也不自动运行测试。

## `build-plan.json`

- `strategy`: `reconfigure`、`incremental` 或 `tilelang-targeted`。
- 选择理由、动作顺序、显式构建命令。
- CMake identity 与 mismatch 列表。
- TileLang changed paths、worker cap、start method。
- 所有阻塞项。

## `source-fingerprint.json`

- repo、branch、commit、base ref。
- dirty status、tracked diff + untracked content SHA256。
- configure 输入文件 SHA256。
- recursive submodule commits。
- `git submodule status` 中的 uninitialized、commit mismatch 或 conflict 都是 blocker。
- xllm_ops 构建前 source HEAD、源码指纹、marker 和已安装 source identity。
- required patch path、SHA256、applied 状态。

## `binary-provenance.json`

- source fingerprint 的 branch、commit、dirty diff SHA。
- CMake、submodule、required patch identity。
- xllm_ops 构建后重新采集的 source/marker identity、构建期间源码是否变化、安装 source
  identity，以及 CPack staging 和安装 OPP 的 payload 文件数、整体 digest、缺失/多余/
  哈希不一致文件。
- 安装 OPP 中动态 kernel config 的文件数、无效 JSON、未进入聚合索引的算子、缺失的
  kernel JSON/`.o`、索引路径不一致项，以及 CPack kernel 相对算子源码的新鲜度。
- 实际策略、构建命令和每条命令退出码。
- 每条命令是否因无输出超时，以及超时前最后一行 family/variant 进度。
- binary path、SHA256、size、ELF `file` 输出和 `ldd -r` 输出。

## `verdict.json`

```json
{
  "status": "PASS | BLOCKED | FAILED",
  "phase": "preflight | build | binary_validation",
  "binary_ready": true,
  "blockers": [],
  "failures": []
}
```

- `PASS`：构建命令成功，binary validation 完整通过，且适用时 xllm_ops marker 与
  OPP payload 完整一致。
- `BLOCKED`：输入或环境不足，构建未安全执行。
- `FAILED`：构建或 binary validation 已执行但失败。
