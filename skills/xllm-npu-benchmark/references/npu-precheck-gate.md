# NPU 性能测试前环境门禁

正式 TTFT/TPOT/TPS 测试前，先判断目标 NPU 是否被其他任务、残留 context、CPU/内存波动污染。未通过门禁的结果不得用于 PR 描述、优化结论或 before/after 对比。

## 必采信息

启动待测服务前创建 `RUN_ROOT/env/` 并保存：

```bash
mkdir -p "$RUN_ROOT/env"
date -Is | tee "$RUN_ROOT/env/precheck.time"
npu-smi info | tee "$RUN_ROOT/env/npu-smi.before.txt"
for id in 0 1 2 3; do
  npu-smi info -t usages -i "$id" | tee "$RUN_ROOT/env/npu-usages.before.npu${id}.txt"
done
pgrep -af 'xllm|vllm|sglang|python|evalscope|msprof' | tee "$RUN_ROOT/env/process.before.txt" || true
free -h | tee "$RUN_ROOT/env/mem.before.txt"
uptime | tee "$RUN_ROOT/env/load.before.txt"
```

启动服务后、正式压测前，再采 3 次空闲态样本，间隔 10 秒：

```bash
for round in 1 2 3; do
  date -Is | tee -a "$RUN_ROOT/env/idle-usages.after-service.txt"
  for id in 0 1 2 3; do
    npu-smi info -t usages -i "$id" | tee -a "$RUN_ROOT/env/idle-usages.after-service.txt"
  done
  sleep 10
done
pgrep -af 'xllm|vllm|sglang|python|evalscope|msprof' | tee "$RUN_ROOT/env/process.after-service.txt" || true
```

压测结束后保存同样的 `npu-smi info`、`npu-smi info -t usages`、`pgrep`、`free -h`、`uptime`，用于判断 run 中是否发生外部波动。

## 判定规则

- 目标卡的 `Health` 必须为 `OK`，服务空闲时 `AICore/NPU Utilization` 应稳定接近 0。
- 目标卡 HBM 占用只能来自本轮待测服务；启动服务前若已有大额 HBM 占用，必须确认来源，否则该卡不能用于正式性能结论。
- `npu-smi info` 进程表中若出现 `ps` 查不到的 PID，按残留或异常 NPU context 处理；先清理或换卡，不能直接做 before/after 结论。
- before/after 两组实验必须使用同一批设备、同一可见卡顺序、同一服务启动参数，并在每组之间重启服务或清状态。
- CPU load、swap、后台 profiling/编译任务必须记录；若压测期间 load 或 swap 明显波动，重跑并标记旧结果为污染样本。
- evalscope 客户端、服务端和 profiling 不要混跑；msprof 采集 run 只用于 profiling 分析，不和无 profiling 性能数直接对比。
- evalscope 正式性能测试必须使用请求级 warmup，例如 `--warmup-num 1` 或 `--warmup-num 2`。`--warmup-num 0` 只能用于冷启动/首请求分析。

## 经验记录

2026-05-28，Qwen35-27B TP=4 MTP=3 复用 `causal_conv1d` 验证前，目标逻辑卡 0-3 的服务空闲态 `AICore=0%`，但 HBM 仍在 76%-77%，且 `npu-smi info` 进程表中存在多个 `ps` 查不到的历史 PID。该状态只能说明服务当前未计算，不能证明环境干净；在这种环境下得到的 evalscope TPOT 不能作为 PR #1536 的最终性能证据。正确流程是先记录门禁结果，清理残留 context 或换用干净卡，再重启服务进行同参数 A/B 测试。
