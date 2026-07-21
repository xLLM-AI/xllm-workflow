# Build Gate Operational Rules

## Multi-candidate lane

baseline、current 和多个候选应使用固定 eval lane，并对每个候选执行完整 gate。候选切换
后重新生成 source fingerprint；不得把上一候选的 PASS verdict 或 binary provenance 复制
给下一候选。

若候选通过 `getenv`、`XLLM_ENABLE_*` 或 `XLLM_SKIP_*` 启用路径，使用 `--build-env`
显式传入并写入 `environment.json`。缺少环境变量证据的结果只能标记为 debug run。

## Required local patches

权重 mmap/safetensors 等本机必需修复必须通过 `--required-patch` 纳入候选身份。验证应覆盖
完整模型加载完成日志，而不只是编译成功或单个请求成功。patch 未应用时 gate 返回
`BLOCKED`，不自动修改源码。

## NPU runtime gate

即将进入 eval 时使用 `--require-npu`，保存 `npu-smi info`、设备节点和相关进程快照。
目标设备是否存在业务占用仍需结合 server/batch runner 的显式设备列表进行确认；仅看到
AICore 空闲不能证明 HBM/context 已清理。

## xllm_ops global OPP gate

`custom_xllm_math` 是多个 checkout/worktree 共享的主机级安装目录。build-gate 会从读取
marker 开始持有 OPP 文件锁，直到 xllm_ops、主构建和构建后验证全部完成。所有通过本
skill 发起的构建因此不能交叉覆盖 vendor；绕过 skill 的手工安装不受该锁保护。

构建后必须重新比较 source HEAD 与 marker，并把 CPack staging 的 `op_impl`、`op_proto`、
`op_api` 与实际安装目录逐文件计算 SHA256。自定义 build dir 位于仓库外时使用：

```bash
--opp-package-root <cpack_staging>/packages/vendors/custom_xllm_math
```

无法找到 staging、marker 未刷新，或 payload 存在缺失、多余、哈希不一致时返回
`FAILED`。不得仅凭 marker 相等或 `ldd -r` 成功进入 benchmark。

AscendC 算子全部编译完成后再统一生成 config。门禁会逐架构检查：

- 单算子 config 的每个 `binInfo.jsonFilePath` 都存在对应 kernel JSON 和 `.o`。
- 单算子 config 中的算子名存在于同目录 `binary_info_config.json`。
- 聚合索引的 `jsonPath`/`binPath` 与单算子 config 一致且文件存在。

这会拦截“后补编某个 kernel，但沿用先前生成的聚合配置”产生的
`ParseDynamicKernelConfig` 运行时错误。CANN 版本升级时还应先做完整编译，及时发现
同步原语等接口是否需要显式 `AscendC::` 命名空间；不能用单算子补编掩盖编译失败。

## Official performance versus profiling

正式性能 run 与 profiling run 必须分开。build verdict 只证明 binary 来源和依赖闭合，
不替代 warmup、公平性、HBM 清理或 accuracy gate。
