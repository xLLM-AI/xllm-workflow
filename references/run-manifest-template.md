# Run Manifest Template

Every formal xLLM NPU evaluation, profiling, accuracy, incident, or optimization
run should include a manifest. The manifest is the first file to inspect when
deciding whether a result is comparable and reproducible.

```markdown
# Run Manifest

## Identity

- run_id:
- date:
- operator_or_agent:
- purpose:
- level: smoke | quick | full
- conclusion_status: pending | pass | fail | inconclusive

## Code

- framework: xllm | vllm-ascend | sglang
- repo_path:
- branch:
- commit:
- base_commit:
- git_status_short:
- submodule_status:
- build_command:
- binary_path:

## Environment

- host:
- container:
- NPU model:
- physical_device_ids:
- ASCEND_RT_VISIBLE_DEVICES:
- CANN version:
- HDK driver version:
- torch_npu version:
- HCCL_IF_BASE_PORT:
- LD_LIBRARY_PATH additions:

## Model

- model_name:
- model_path:
- tokenizer_path:
- draft_model_path:
- dtype:
- tensor_parallel:
- pipeline_parallel:
- speculative_tokens:

## Service

- api_url:
- startup_script:
- startup_command:
- service_pid:
- log_dir:
- healthcheck_command:
- healthcheck_result:
- graph_enabled:
- schedule_overlap:
- chunked_prefill:
- prefix_cache:
- block_size:
- max_memory_utilization:
- max_tokens_per_batch:
- max_seqs_per_batch:

## Workload

- dataset:
- dataset_path:
- input_tokens:
- output_tokens:
- parallel:
- number:
- warmup_num:
- stream:
- max_tokens:
- max_prompt_length:
- temperature:
- top_p:
- top_k:
- seed:
- extra_body:

## Artifacts

- env_snapshot_dir:
- service_artifact_dir:
- perf_artifact_dir:
- accuracy_artifact_dir:
- profiling_artifact_dir:
- metrics_json:
- report_md:

## Comparison

- baseline_run_id:
- baseline_commit:
- baseline_metrics:
- current_metrics:
- delta:
- fairness_notes:

## Notes

- known_risks:
- deviations:
- next_steps:
```

Rules:

- A result without commit, startup command, workload, warmup, and raw artifact
  paths is a debug result, not formal evidence.
- A dirty worktree is allowed only if the diff is saved and intentionally part
  of the experiment.
- Profiling runs are not directly comparable with non-profiling performance
  runs; use them for root-cause analysis.
