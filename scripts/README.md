# scripts/ — Deterministic Engine

Automation scripts for compilation, service launch, performance testing, and accuracy testing.
These scripts are **deterministic** — LLM must not modify their logic. Changes require human review.

## Contents

- `query.py` — Query model dossiers in `reference/pr_history/` by model, keyword, or path
- `collect_evalscope_results.py` — Collect and normalize evalscope benchmark results
- `compare_npu_benchmark.py` — Cross-framework NPU benchmark comparison
- `validate_framework_cli.py` — Validate framework CLI parameters

## Principles

- Scripts here are cross-skill shared utilities; skill-specific scripts stay in their skill's `scripts/` subdirectory
- All scripts must be runnable from the repository root
- Parameter changes go into `config.json`, not hardcoded in scripts