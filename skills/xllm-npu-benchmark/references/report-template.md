# A/B Benchmark 报告模板

本文件提供 xLLM vs vLLM-Ascend A/B 对比报告的完整模板，
包含总报告和分并发报告两部分。生成报告时按实际数据填充占位符。

> 中文内容通过 Python unicode escape 方式写入，避免 Windows SSH 管道编码问题。
> 具体方法参见 `xllm-npu-report-writer` SKILL.md 的"中文报告生成方法"章节。

## 1. 总报告模板

存放路径：`<artifact_root>/report.md`

```markdown
# {模型名} xLLM vs vLLM-Ascend 性能对比总报告

## 测试概要

- **测试日期**: {YYYY-MM-DD}
- **运行模式**: {full|incremental}（{full: 两个框架均为本次新跑结果 | incremental: xLLM 新跑, vLLM 历史基线}）
- **模型**: {模型名}
- **Tokenizer**: {tokenizer路径}
- **TP**: {TP值} ({描述})
- **并发数**: {parallel列表}
- **请求数**: {number规则}
- **Warmup**: {warmup数}
- **Input/Output Tokens**: {input}/{output}
- **Dataset**: {dataset类型}
- **采样参数**: {采样参数描述}

## 环境信息

| 项目 | xLLM | vLLM-Ascend |
|------|------|-------------|
| 容器 | {xllm容器} | {vllm容器} |
| evalscope容器 | {evalscope容器} | {evalscope容器} |
| 端口 | {xllm端口} | {vllm端口} |
| 模型名 | {xllm模型名} | {vllm模型名} |
| MTP | {MTP配置} | {MTP配置} |
| Graph模式 | {graph配置} | {graph配置} |
| max_memory_utilization | {值} | {值} |
| max_tokens_per_batch | {值} | {值} |
| max_seqs | {值} | {值} |
| block_size | {值} | {值} |
| NPU设备 | {NPU描述} | {NPU描述} |
| 内存 | {内存描述} | {内存描述} |

## 配置一致性检查

| 配置项 | 一致性 | 说明 |
|--------|--------|------|
| 模型权重 | {一致/不一致} | {路径} |
| Tokenizer | {一致/不一致} | {路径} |
| TP | {一致/不一致} | {值} |
| NPU设备 | {一致/不一致} | {描述} |
| 内存利用率 | {一致/不一致} | {值} |
| MTP | {一致/不一致} | {配置} |
| 采样参数 | {一致/不一致} | {参数} |
| Workload | {一致/不一致} | {描述} |
| Warmup | {一致/不一致} | {值} |

## TTFT 对比 (ms)

| 并发 | 指标 | xLLM | vLLM-Ascend | 差异 | 胜出 |
|------|------|------|-------------|------|------|
| {P} | avg | {值} | {值} | {差异%} | {胜出方} |
| {P} | p50 | {值} | {值} | {差异%} | {胜出方} |
| {P} | p90 | {值} | {值} | {差异%} | {胜出方} |
| {P} | p99 | {值} | {值} | {差异%} | {胜出方} |

（为每个并发场景重复上述4行）

## TPOT 对比 (ms)

| 并发 | 指标 | xLLM | vLLM-Ascend | 差异 | 胜出 |
|------|------|------|-------------|------|------|
| {P} | avg | {值} | {值} | {差异%} | {胜出方} |
| {P} | p50 | {值} | {值} | {差异%} | {胜出方} |
| {P} | p90 | {值} | {值} | {差异%} | {胜出方} |
| {P} | p99 | {值} | {值} | {差异%} | {胜出方} |

（为每个并发场景重复上述4行）

## ITL 对比 (ms)

| 并发 | xLLM | vLLM-Ascend | 差异 | 胜出 |
|------|------|-------------|------|------|
| {P} | {值} | {值} | {差异%} | {胜出方} |

## 输出吞吐量对比 (tok/s)

| 并发 | xLLM | vLLM-Ascend | 差异 | 胜出 |
|------|------|-------------|------|------|
| {P} | {值} | {值} | {差异%} | {胜出方} |

## 总吞吐量对比 (tok/s)

| 并发 | xLLM | vLLM-Ascend | 差异 | 胜出 |
|------|------|-------------|------|------|
| {P} | {值} | {值} | {差异%} | {胜出方} |

## 请求吞吐量对比 (req/s)

| 并发 | xLLM | vLLM-Ascend | 差异 | 胜出 |
|------|------|-------------|------|------|
| {P} | {值} | {值} | {差异%} | {胜出方} |

## MTP 效率对比

| 并发 | 指标 | xLLM | vLLM-Ascend |
|------|------|------|-------------|
| {P} | Decoded Tok/Iter | {值} | {值} |
| {P} | Spec. Accept Rate | {值%} | {值%} |

## 扩展性分析

### xLLM 吞吐量随并发变化

{ASCII 柱状图}

### vLLM-Ascend 吞吐量随并发变化

{ASCII 柱状图}

### TPOT 随并发变化趋势

{ASCII 柱状图}

## 综合对比汇总

| 维度 | xLLM 胜出项 | vLLM 胜出项 |
|------|------------|------------|
| TTFT (avg) | {N}/{total} ({百分比}) | {N}/{total} ({百分比}) |
| TPOT (avg) | {N}/{total} ({百分比}) | {N}/{total} ({百分比}) |
| Output Throughput | {N}/{total} ({百分比}) | {N}/{total} ({百分比}) |
| Total Throughput | {N}/{total} ({百分比}) | {N}/{total} ({百分比}) |

## 公平性门禁

- **同一模型权重**: {PASS/FAIL}
- **同一 Tokenizer**: {PASS/FAIL}
- **同一 NPU 设备**: {PASS/FAIL} ({描述})
- **同一采样参数**: {PASS/FAIL}
- **同一 Workload**: {PASS/FAIL}
- **同一 Warmup**: {PASS/FAIL} ({值})
- **请求级 Warmup**: {PASS/FAIL} ({参数})
- **环境门禁**: {PASS/FAIL} ({描述})

## 最终结论

**Verdict: {PASS/FAIL/INCONCLUSIVE/SMOKE_ONLY}**

{结论描述，列出关键数据点}

**结果等级**: {formal-pr|smoke|sota-report}

## 产物路径

- 分并发报告: `<artifact_root>/parallel_{P}/comparison/report.md`
- 总报告: `<artifact_root>/report.md`
- xLLM evalscope 原始结果: `<artifact_root>/parallel_{P}/xllm/perf/`
- vLLM evalscope 原始结果: `<artifact_root>/parallel_{P}/vllm-ascend/perf/`
- 环境门禁: `<artifact_root>/env/`
- xLLM 服务日志: `<artifact_root>/xllm_service_log/`
- vLLM 服务日志: `<artifact_root>/vllm_service_log/`
```

## 2. 分并发报告模板

存放路径：`<artifact_root>/parallel_{parallel}/comparison/report.md`

```markdown
# {模型名} 性能对比报告 (parallel={P})

## 测试信息

- **测试日期**: {YYYY-MM-DD}
- **模型**: {模型名}
- **Tokenizer**: {tokenizer路径}
- **TP**: {TP值} ({描述})
- **并发数**: {P}
- **请求数**: {number}
- **Warmup**: {warmup数}
- **Input/Output Tokens**: {input}/{output}
- **Dataset**: {dataset类型}
- **温度**: {温度值} ({采样参数})

## 环境信息

| 项目 | xLLM | vLLM-Ascend |
|------|------|-------------|
| 容器 | {xllm容器} | {vllm容器} |
| evalscope容器 | {evalscope容器} | {evalscope容器} |
| 端口 | {xllm端口} | {vllm端口} |
| 模型名 | {xllm模型名} | {vllm模型名} |
| MTP | {MTP配置} | {MTP配置} |
| Graph模式 | {graph配置} | {graph配置} |
| max_memory_utilization | {值} | {值} |
| max_tokens_per_batch | {值} | {值} |
| max_seqs | {值} | {值} |
| block_size | {值} | {值} |

## 配置一致性检查

| 配置项 | 一致性 | 说明 |
|--------|--------|------|
| 模型权重 | {一致/不一致} | {路径} |
| Tokenizer | {一致/不一致} | {路径} |
| TP | {一致/不一致} | {值} |
| NPU设备 | {一致/不一致} | {描述} |
| 内存利用率 | {一致/不一致} | {值} |
| MTP | {一致/不一致} | {配置} |
| 采样参数 | {一致/不一致} | {参数} |
| Workload | {一致/不一致} | {描述} |

## TTFT 对比 (ms)

| 指标 | xLLM | vLLM-Ascend | 差异 | 胜出 |
|------|------|-------------|------|------|
| avg | {值} | {值} | {差异%} | {胜出方} |
| p50 | {值} | {值} | {差异%} | {胜出方} |
| p90 | {值} | {值} | {差异%} | {胜出方} |
| p99 | {值} | {值} | {差异%} | {胜出方} |

## TPOT 对比 (ms)

| 指标 | xLLM | vLLM-Ascend | 差异 | 胜出 |
|------|------|-------------|------|------|
| avg | {值} | {值} | {差异%} | {胜出方} |
| p50 | {值} | {值} | {差异%} | {胜出方} |
| p90 | {值} | {值} | {差异%} | {胜出方} |
| p99 | {值} | {值} | {差异%} | {胜出方} |

## ITL 对比 (ms)

| 指标 | xLLM | vLLM-Ascend | 差异 | 胜出 |
|------|------|-------------|------|------|
| avg | {值} | {值} | {差异%} | {胜出方} |

## 吞吐量对比

| 指标 | xLLM | vLLM-Ascend | 差异 | 胜出 |
|------|------|-------------|------|------|
| Output Throughput (tok/s) | {值} | {值} | {差异%} | {胜出方} |
| Total Throughput (tok/s) | {值} | {值} | {差异%} | {胜出方} |
| Req Throughput (req/s) | {值} | {值} | {差异%} | {胜出方} |

## MTP 效率

| 指标 | xLLM | vLLM-Ascend |
|------|------|-------------|
| Decoded Tok/Iter | {值} | {值} |
| Spec. Accept Rate | {值%} | {值%} |

## 结论

{胜出方} 在 parallel={P} 场景下{全面优于/优于/持平}对方：
- TTFT 平均{快/慢} **{百分比}**
- TPOT 平均{快/慢} **{百分比}**
- 输出吞吐量{高/低} **{百分比}**
```

## 3. 差异计算规则

- **延迟指标（TTFT、TPOT、ITL）**：`差异 = (xLLM - vLLM) / vLLM * 100%`
  - 负值表示 xLLM 更优，正值表示 vLLM 更优
- **吞吐指标（Output/Total/Req Throughput）**：`差异 = (xLLM - vLLM) / vLLM * 100%`
  - 正值表示 xLLM 更高，负值表示 xLLM 较低
- **胜出判定**：TTFT/TPOT/ITL 取低者胜出，吞吐量取高者胜出

## 4. incremental 模式标注

incremental 模式下，报告中必须明确标注：
- xLLM 为本次新跑结果
- vLLM-Ascend 为历史基线结果（引用来源路径）
- 在测试概要和结论中均需注明
