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

## Official performance versus profiling

正式性能 run 与 profiling run 必须分开。build verdict 只证明 binary 来源和依赖闭合，
不替代 warmup、公平性、HBM 清理或 accuracy gate。
