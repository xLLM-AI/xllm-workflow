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

模型路径依赖特定 xllm_ops 算子时，还应通过 `--required-opp-symbol` 声明 ACLNN 导出符号。
例如 Qwen3.5 GDN 路径同时要求 `aclnnMegaChunkGdn` 和
`aclnnMegaChunkGdnGetWorkspaceSize`，防止 CANN 版本探测错误导致算子被静默跳过。

## NPU runtime gate

即将进入 eval 时使用 `--require-npu`，保存 `npu-smi info`、设备节点和相关进程快照。
目标设备是否存在业务占用仍需结合 server/batch runner 的显式设备列表进行确认；仅看到
AICore 空闲不能证明 HBM/context 已清理。

## xllm_ops global OPP gate

`custom_xllm_math` 是多个 checkout/worktree 共享的主机级安装目录。build-gate 会从读取
marker 开始持有 OPP 文件锁，直到 xllm_ops、主构建和构建后验证全部完成。所有通过本
skill 发起的构建因此不能交叉覆盖 vendor；绕过 skill 的手工安装不受该锁保护。

完整 `reconfigure` 必须保留框架官方构建顺序。对 xLLM，执行一次
`--configure-command`，由 `setup.py` 按 `TileLang → CMake/xllm_ops → xLLM` 编排；即使
marker 不匹配，也不得先执行独立 `--xllm-ops-command`。独立 xllm_ops 命令仅用于不进入
full configure 的 incremental/targeted 策略。两种路径都必须通过相同的构建后 payload
验证。

构建前同时比较 source HEAD 与 marker、源码指纹与安装目录中的
`.xllm_ops_source_identity.json`。源码指纹覆盖 HEAD、tracked diff 和未跟踪源文件；因此
本地 patch 或构建脚本改动会选择性触发 xllm_ops 重编，不要求清空无关下载和第三方缓存。

构建后必须重新采集源码指纹，确认构建过程没有改写源码，再把 CPack staging 的
`op_impl`、`op_proto`、`op_api` 与实际安装目录逐文件计算 SHA256。自定义 build dir
位于仓库外时使用：

```bash
--opp-package-root <cpack_staging>/packages/vendors/custom_xllm_math
```

无法找到 staging、marker 未刷新、source identity 不一致，或 payload 存在缺失、多余、
哈希不一致时返回 `FAILED`。不得仅凭 marker 相等或 `ldd -r` 成功进入 benchmark。

AscendC 算子全部编译完成后再统一生成 config。门禁会逐架构检查：

- CPack staging 中 kernel `.o` 的时间不早于同名算子目录内最新源文件，防止构建系统只
  重打包旧 kernel。
- 单算子 config 的每个 `binInfo.jsonFilePath` 都存在对应 kernel JSON 和 `.o`。
- 单算子 config 中的算子名存在于同目录 `binary_info_config.json`。
- 聚合索引的 `jsonPath`/`binPath` 与单算子 config 一致且文件存在。

这会拦截“后补编某个 kernel，但沿用先前生成的聚合配置”产生的
`ParseDynamicKernelConfig` 运行时错误。CANN 版本升级时还应先做完整编译，及时发现
同步原语等接口是否需要显式 `AscendC::` 命名空间；不能用单算子补编掩盖编译失败。

## Official performance versus profiling

正式性能 run 与 profiling run 必须分开。build verdict 只证明 binary 来源和依赖闭合，
不替代 warmup、公平性、HBM 清理或 accuracy gate。
