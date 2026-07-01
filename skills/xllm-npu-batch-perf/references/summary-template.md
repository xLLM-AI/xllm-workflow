# Batch Performance Summary

**Date**: YYYY-MM-DD
**Batch**: <batch_name>
**Host**: <ssh_host> (<ip>)
**xLLM Container**: <xllm_container>
**evalscope Container**: <evalscope_container>
**Devices**: NPU <device_ids> (TP=<tp>)
**Port**: <start_port>

## Configuration

| Parameter | Value |
|---|---|
| max_memory_utilization | 0.70 |
| max_tokens_per_batch | 32768 |
| max_seqs_per_batch | 8 |
| block_size | 128 |
| communication_backend | lccl |
| enable_graph | true |
| enable_prefix_cache | true |
| enable_chunked_prefill | true |
| enable_schedule_overlap | true |
| enable_shm | true |
| num_speculative_tokens | 3 (MTP models) |
| input_tokens | 2048 |
| output_tokens | 2048 |
| parallel_list | 1,2,4 |
| number | 4 (per parallel) |
| warmup_num | 2 |

## Results

| Model | TP | MTP | Parallel | TTFT (ms) | TPOT (ms) | Output tok/s | Total tok/s | Spec Accept |
|---|---|---|---|---|---|---|---|---|
| **Qwen3.5-4B** | 2 | off | 1 | 266.1 | 7.84 | 122.7 | 245.5 | - |
| | | | 2 | 162.4 | 8.63 | 228.2 | 456.4 | - |
| | | | 4 | 309.2 | 10.34 | 381.3 | 762.6 | - |
| **Qwen3.5-27B** | 2 | on | 1 | 519.0 | 13.40 | 72.3 | 145.3 | 66.9% |
| | | | 2 | 470.8 | 14.88 | 130.3 | 264.1 | 67.0% |
| | | | 4 | 612.0 | 16.99 | 220.7 | 457.8 | 66.9% |
| **Qwen3.5-35B-A3B** | 2 | on | 1 | 305.1 | 7.21 | 132.6 | 265.2 | 66.8% |
| | | | 2 | 186.7 | 8.13 | 228.6 | 457.3 | 68.7% |
| | | | 4 | 231.1 | 9.67 | 403.6 | 809.7 | 69.8% |
| **Qwen3.6-27B** | 2 | on | 1 | 518.9 | 12.55 | 78.1 | 200.1 | 68.8% |
| | | | 2 | 471.4 | 13.39 | 145.9 | 328.8 | 70.0% |
| | | | 4 | 588.6 | 16.38 | 231.5 | 648.3 | 68.2% |

## Key Findings

- **<best_model>** 全并发最优：<reason>
- **<other_findings>**
- 所有模型并发增加后 TPOT 退化幅度可控（P=1→P=4 约 +30~35%）

## Notes

- <note_1>
- <note_2>
