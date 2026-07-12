# Getting Started

This guide installs the canonical skills and walks through a synthetic, non-NPU experiment lifecycle. It does not start a model service or claim hardware performance.

## 1. Choose the workspace mode

From the workflow repository, initialize or reuse `code/xllm` and link project skills into `.agents/skills`:

```bash
python scripts/init_xllm_workspace.py
```

To run the agent from an existing xLLM checkout, install the project skills into the selected agent directory:

```bash
python scripts/init_xllm_workspace.py --mode xllm --agent codex
```

The installer discovers exactly the canonical directories declared in `skills/catalog.json`.

## 2. Start the agent

For repository-root mode:

```bash
codex
```

For xLLM checkout mode:

```bash
cd code/xllm
codex
```

Start a new task after refresh so the agent receives current skill metadata.

## 3. Choose the primary workflow

- New or interrupted run state: `xllm-experiment-lifecycle`.
- Open-ended xLLM optimization: `xllm-npu-sota-loop`, delegating run state to lifecycle.
- One performance test against a ready service: `xllm-npu-perf-runner`.
- Performance plus accuracy with complete artifacts: `xllm-npu-eval-runner`.

See the [capability index](../skills/README.md) for every route.

## 4. Create a synthetic lifecycle

Copy [`experiment.example.yaml`](../reference/io_specs/experiment.example.yaml), set a local run root and a source checkout, and keep `environment.require_npu: false` for a synthetic check. Then follow the canonical commands in the [lifecycle skill](../skills/xllm-experiment-lifecycle/SKILL.md):

```text
preflight -> run create -> specialist artifacts -> attempt add
          -> run validate -> export evidence -> gate all
          -> finalize -> retention review -> archive
```

The repository test `tests/test_lifecycle_skill_cli.py` executes this lifecycle through real CLI subprocesses without starting a service or using an NPU.

## 5. Continue with real work

Before a real run, pin model, binary, checkout, hardware, workload, sampling, and evidence level. Use the [standard workflow](npu-ai-coding-standard-workflow.md) and preserve the support boundary: xLLM is complete; vLLM-Ascend and SGLang are limited to explicitly declared adapter or artifact scopes.

## Validate the repository

```bash
python scripts/validate_skill_catalog.py
python scripts/render_skill_docs.py --check
pytest -q
git diff --check
```
