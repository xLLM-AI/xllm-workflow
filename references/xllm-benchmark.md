# xLLM Benchmark Baseline

> Update this file whenever new baseline results are available. The xllm-npu-eval-runner skill can fetch this file for a quick baseline check; formal comparisons should use xllm-npu-benchmark.

---

## Qwen35-27B

### TP4-MTP3-CHUNKED

#### Performance

| Metric | Parallel=1 | Parallel=5 |
|---|---|---|
| Output Throughput (tok/s) | 66.56 | - |
| Total Throughput (tok/s) | 1366.82 | - |
| TTFT (ms) | 2397.49 | - |
| TPOT (ms) | 12.33 | - |
| ITL (ms) | 36.82 | - |
| Avg Output Tokens | 1024.0 | - |
| Decoded Tok/Iter | 3.17 | - |
| Spec. Accept Rate | 0.67 | - |

#### Accuracy (ceval full)

| Dataset | Score |
|---|---|
| ceval (overall) | 91.75 |

#### Accuracy (ceval smoke subset)

| Dataset | Score |
|---|---|
| ceval-computer_network | 0.8947 |
| ceval-operating_system | 0.9474 |
| ceval-marxism | 1 |

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
