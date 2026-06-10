# xLLM Benchmark Baseline

> Update this file whenever new baseline results are available. The xllm-npu-eval-runner skill can fetch this file for a quick baseline check; formal comparisons should use xllm-npu-benchmark.

---

## Qwen35-27B

### TP4-MTP3-CHUNKED

#### Performance

| Metric | Parallel=1 | Parallel=5 |
|---|---|---|
| Output Throughput (tok/s) | 64.49 | - |
| Total Throughput (tok/s) | 1324.50 | - |
| TTFT (ms) | 2357.43 | - |
| TPOT (ms) | 12.85 | - |
| ITL (ms) | 38.07 | - |
| Avg Output Tokens | 1024.0 | - |
| Decoded Tok/Iter | 2.96 | - |
| Spec. Accept Rate | 0.6627 | - |

#### Accuracy (ceval full)

| Dataset | Score |
|---|---|
| ceval (overall) | - |

#### Accuracy (ceval smoke subset)

| Dataset | Score |
|---|---|
| ceval-computer_network | - |
| ceval-operating_system | - |
| ceval-marxism | - |

---

### TP4-MTP5-CHUNKED

#### Performance

| Metric | Parallel=1 | Parallel=5 |
|---|---|---|
| Output Throughput (tok/s) | 62.10 | - |
| Total Throughput (tok/s) | 1275.59 | - |
| TTFT (ms) | 2296.54 | - |
| TPOT (ms) | 13.51 | - |
| ITL (ms) | 46.72 | - |
| Avg Output Tokens | 1024.0 | - |
| Decoded Tok/Iter | 3.48 | - |
| Spec. Accept Rate | 0.7128 | - |

#### Accuracy (ceval full)

| Dataset | Score |
|---|---|
| ceval (overall) | - |

#### Accuracy (ceval smoke subset)

| Dataset | Score |
|---|---|
| ceval-computer_network | - |
| ceval-operating_system | - |
| ceval-marxism | - |

---

<!--
## Adding New Configurations

Copy the block below and fill in the values:

### <CONFIG_NAME>

#### Performance

| Metric | Parallel=1 | Parallel=5 |
|---|---|---|
| Output Throughput (tok/s) | - | - |
| Total Throughput (tok/s) | - | - |
| TTFT (ms) | - | - |
| TPOT (ms) | - | - |
| ITL (ms) | - | - |
| Avg Output Tokens | - | - |
| Decoded Tok/Iter | - | - |
| Spec. Accept Rate | - | - |

#### Accuracy (ceval full)

| Dataset | Score |
|---|---|
| ceval (overall) | - |

#### Accuracy (ceval smoke subset)

| Dataset | Score |
|---|---|
| ceval-computer_network | - |
| ceval-operating_system | - |
| ceval-marxism | - |
-->
