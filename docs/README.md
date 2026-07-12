# Documentation Hub

Use this page to find current operating guidance. Documents under `docs/pr12/` and `docs/pr14/` are preserved design records, not the default user workflow.

## Start here

- [Getting started](getting-started.md) — install skills and complete a synthetic lifecycle.
- [Standard NPU AI coding workflow](npu-ai-coding-standard-workflow.md) — evidence-driven phases and review gates.
- [Skill capability index](../skills/README.md) — choose a canonical entry by role or domain.

## Run workflows

- [Experiment lifecycle](../skills/xllm-experiment-lifecycle/SKILL.md)
- [Performance optimization](../skills/xllm-npu-sota-loop/SKILL.md)
- [Service-only lifecycle](../skills/xllm-npu-server-manager/SKILL.md)
- [Mixed evaluation](../skills/xllm-npu-eval-runner/SKILL.md) and [benchmark review](../skills/xllm-npu-benchmark/SKILL.md)
- [Profiling](../skills/xllm-npu-profiler/SKILL.md), [pipeline analysis](../skills/xllm-npu-pipeline-analysis/SKILL.md), and [incident diagnosis](../skills/xllm-npu-incident-triage/SKILL.md)
- [Operator migration](../skills/xllm-npu-triton-migration/SKILL.md) and [runtime integration](../skills/xllm-npu-xllm-ops-integration/SKILL.md)

## Understand the system

- [Repository and evidence map](architecture/repository-map.md)
- [Generated skill architecture](architecture/skill-map.md)
- [IO schemas and examples](../reference/io_specs/)
- [Model and PR history](../reference/pr_history/)

Support labels used throughout the documentation:

- **Supported:** complete xLLM workflow on Ascend.
- **Experimental adapter:** a declared build or evidence adapter, not full interchangeability.
- **Artifact analysis only:** existing artifacts can be analyzed without claiming end-to-end serving support.
- **Internal / explicit-only:** not eligible for implicit primary routing.

## Maintain the repository

- [Add or change a skill](maintainers/adding-or-changing-a-skill.md)
- [Deterministic scripts](../scripts/README.md)
- [Catalog and generated-document workflow](maintainers/adding-or-changing-a-skill.md#6-render-generated-documentation)
- [Agent constraints and routing contract](../AGENTS.md)

## Design history

- [PR12 taxonomy and routing record](pr12/PLAN.md) — historical design and validation evidence.
- [PR14 information architecture plan](pr14/PLAN.md) — design record for the current navigation work.

Historical records remain link-stable. Current operating guidance is linked from the sections above.
