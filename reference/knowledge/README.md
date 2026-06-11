# reference/knowledge/ — Domain Knowledge

Immutable domain rules that inform Agent decisions.

## Contents

(Directory currently stores domain knowledge rules. NPU hardware specs are now in `config.json` under `static.npu_specs`.)

## Principles

- Files here are **read-only references** — never modify based on a single run
- New domain knowledge (operator limits, memory allocation strategies) is added here, not in skill-local references
- NPU hardware specs: read from `config.json` → `static.npu_specs`
- For code style conventions, see `reference/code-style/`
- For interface contracts, see `reference/io_specs/`