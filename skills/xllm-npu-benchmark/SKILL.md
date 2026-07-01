---
name: xllm-npu-benchmark
description: 在昇腾 NPU 上进行 xLLM、vLLM-Ascend、SGLang NPU 等 OpenAI-compatible serving 框架的公平推理基准测试和性能结论审查。当用户需要比较框架、比较 before/after、搜索满足 TTFT/TPOT/SLA 的最大 QPS、判断 benchmark 是否可写入 PR 或报告时使用。当前脚本优先支持 xLLM 与 vLLM-Ascend 对比，可扩展到更多框架。
---

# xLLM NPU 基准测试

用这个 skill 判断 benchmark 是否公平、可比、可复现，并输出可写入 PR / 报告的性能结论。

## 职责边界

- `xllm-npu-eval-runner`：启动/复用服务、执行 evalscope、收集原始 artifacts。
- 本 skill：审查 artifacts、公平性、SLA、候选搜索和性能结论。
- `xllm-npu-profiler`：定位 TTFT/TPOT/TPS 背后的 NPU timeline 根因。
- `xllm-npu-accuracy-debug`：性能改动可能影响正确性时验证精度。

如果用户只要求“跑一下服务/评测”，先用 `xllm-npu-eval-runner`；如果用户要求“公平比较/性能结论/PR 证据”，使用本 skill。

## 子 Skill 依赖

| 职责 | 使用 |
|---|---|
| 报告生成 | `xllm-npu-report-writer`（模板：`references/report-template.md`） |

## 必读规则

正式 benchmark 必须满足这些条件，否则只能标记为 `smoke/debug`：

- 同一模型权重、tokenizer、dtype、量化方案、采样参数、workload、请求数、并发、warmup 和 SLA。
- 同一 NPU 型号、卡数、可见卡顺序、CANN/Driver 记录方式；before/after 必须记录同一批设备。
- 每个候选都保存启动命令、框架 commit/package、容器镜像或环境、原始 evalscope 输出、结构化 metrics、服务日志和 run manifest。
- 正式稳态性能必须使用请求级 warmup，例如 evalscope `--warmup-num 1` 或更高；冷启动/首请求结果不能和稳态结果直接比较。
- profiling run 只用于瓶颈诊断，不得直接和无 profiling 的正式性能 run 比较。
- 不要比较 tuned xLLM 与 default vLLM-Ascend/SGLang，或反过来；每个框架都要在相同目标下独立调优。

共享产物契约：

- [`../../reference/io_specs/perf-artifact-schema.md`](../../reference/io_specs/perf-artifact-schema.md)
- [`../../reference/io_specs/run-manifest-template.md`](../../reference/io_specs/run-manifest-template.md)
- [`references/npu-fairness-rules.md`](references/npu-fairness-rules.md)

## 按需加载 References

只在任务涉及对应场景时加载，避免把主流程变成长手册：

| 场景 | 加载 |
|---|---|
| 性能测试前环境门禁、残留 NPU context、污染样本判定 | [`references/npu-precheck-gate.md`](references/npu-precheck-gate.md) |
| xLLM 和 baseline 框架需要不同容器或依赖环境 | [`references/container-ab-benchmark.md`](references/container-ab-benchmark.md) |
| evalscope 命令模板、YAML 配置、QPS 搜索模板 | [`references/benchmark-runbook.md`](references/benchmark-runbook.md) |
| MTP/speculative decoding、接受率、draft model、`/vars` counter | [`references/mtp-benchmark-lessons.md`](references/mtp-benchmark-lessons.md) |
| chunked prefill 是否真正生效、prefill profiling 对比 | [`references/chunked-prefill-benchmark.md`](references/chunked-prefill-benchmark.md) |
| 报告格式规范：中文撰写、avg/p50/p90/p99 完整指标、分并发报告 + 总报告结构 | [`references/report-format-spec.md`](references/report-format-spec.md) |
| A/B 对比报告模板：总报告 + 分并发报告的完整占位符模板 | [`references/report-template.md`](references/report-template.md) |
| 标准 prompt 模板：支持 full（全量对比）和 incremental（增量对比）两种模式 | [`references/benchmark-prompt-template.md`](references/benchmark-prompt-template.md) |

## 工作流

### 1. 明确目标

先把目标写成可执行条件：

- 框架：xLLM vs vLLM-Ascend / SGLang NPU / before-after。
- 模型、TP/PP/EP、NPU 型号和卡数。
- workload：数据集、input/output tokens、parallel、number、sampling。
- 目标：固定 QPS、最大 QPS、TTFT/TPOT/TPS、吞吐或 SLA。
- 输出等级：`smoke`、`formal-pr`、`sota-report`。

### 2. 做门禁

正式性能测试前必须做环境门禁。至少保存：

- `npu-smi info` 和目标卡 `npu-smi info -t usages` 的 before/after；
- 服务启动前、启动后空闲态、压测后的进程表；
- CPU load、memory、swap；
- CANN、Driver、torch_npu、框架 commit/package、容器镜像。

如果目标卡有未知 HBM 占用、`ps` 查不到的 NPU PID、服务空闲态 AICore 不稳定接近 0，结论标记为 `INCONCLUSIVE` 或 `smoke/debug`，先清理或换卡重跑。

### 3. 规范 workload

正式对比必须使用同一份 JSONL 或同一组 evalscope 参数。记录每行请求是否是完整 OpenAI request body，以及是否启用 streaming。

示例：

```json
{"prompt": "请总结这篇文章的要点。", "output_len": 256}
{"prompt": [{"role": "user", "content": "解释量子纠缠。"}], "output_len": 512}
```

### 4. 独立调优每个框架

按相同 workload 和 SLA 搜索候选。建议层级：

| 层级 | 用途 | 候选数 |
|---|---|---|
| Tier 1 | smoke / 快速回归 | <= 3 |
| Tier 2 | 默认正式扫描 | <= 10 |
| Tier 3 | 穷举搜索 | <= 30 |

至少记录每个候选的完整启动命令、失败原因和是否满足 SLA。常见调优维度：

- 并行：TP / PP / EP。
- 图模式：eager / npugraph_ex / ge。
- KV cache：block size / max model len / PA layout。
- 调度：max seqs / chunk prefill / PD 分离。
- 内存：memory utilization / xTensor pool。
- 算法：speculative decoding / EPLB / prefix cache。

### 5. 归一化和比较

脚本入口：

- [`scripts/collect_evalscope_results.py`](scripts/collect_evalscope_results.py)：递归收集 evalscope `benchmark_summary.json` / `benchmark_percentile.json`，归一化为 JSONL。
- [`scripts/compare_npu_benchmark.py`](scripts/compare_npu_benchmark.py)：比较 xLLM 和 vLLM-Ascend 候选，输出 Markdown/CSV/JSONL。
- [`scripts/validate_framework_cli.py`](scripts/validate_framework_cli.py)：检查框架 CLI 和关键参数是否可用。

典型命令：

```bash
python scripts/collect_evalscope_results.py \
  --root /path/to/xllm/evalscope/results \
  --framework xllm \
  --output-jsonl /path/to/xllm_results.jsonl \
  --output-summary /path/to/xllm_summary.md \
  --sla-ttft-ms 500 \
  --sla-tpot-ms 50

python scripts/collect_evalscope_results.py \
  --root /path/to/vllm/evalscope/results \
  --framework vllm-ascend \
  --output-jsonl /path/to/vllm_results.jsonl

python scripts/compare_npu_benchmark.py \
  --xllm-results /path/to/xllm_results.jsonl \
  --vllm-results /path/to/vllm_results.jsonl \
  --output-dir /path/to/comparison/
```

排序规则：SLA 通过 > 请求吞吐 > 输出 token 吞吐 > p50 TTFT > p50 TPOT。

### 6. 输出结论

结论必须区分"数据事实"和"可写入 PR 的判断"。缺少门禁、warmup、原始日志、manifest 或公平性证据时，不要写百分比收益。

#### 报告生成

委托 `xllm-npu-report-writer` 生成报告，传入本 skill 的模板：

```
加载 xllm-npu-report-writer，参数：
  Run Root: <artifact_root>
  template_path: skills/xllm-npu-benchmark/references/report-template.md
  report_type: benchmark
```

report-writer 将按 `references/report-template.md` 的结构生成：
- 总报告：`<artifact_root>/report.md`
- 分并发报告：`<artifact_root>/parallel_{P}/comparison/report.md`

报告格式同时遵循 `references/report-format-spec.md` 的规范（中文、avg/p50/p90/p99）。

#### 结论摘要（嵌入报告最终结论章节）

```markdown
## Benchmark Conclusion

- Verdict: PASS / FAIL / INCONCLUSIVE / SMOKE_ONLY
- Comparison: xLLM <commit> vs <baseline framework> <commit/version>
- Workload: <dataset>, input=<n>, output=<n>, parallel=<n>, number=<n>, warmup=<n>
- SLA: TTFT p99 <= <ms>, TPOT p99 <= <ms>
- Fairness gate: PASS / FAIL, with reason
- Winner: <framework/config>, with metric summary
- Caveats: <known risks, contaminated samples, missing artifacts>

## Best Results

| Framework | Candidate | QPS | Req/s | Output tok/s | p50 TTFT | p99 TTFT | p50 TPOT | p99 TPOT | SLA |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|

## Artifacts

- Run manifest:
- Raw evalscope:
- Normalized JSONL:
- Comparison CSV:
- Service logs:
- Environment gate:
- Profiling, if used:
```

## 返回要求

最终回复用户时包含：

- 使用的测试等级和是否可作为正式结论；
- 最优配置和关键指标；
- 是否满足 SLA；
- 公平性门禁结果；
- 产物路径；
- 不能下结论的原因，如果有。
