# reference/knowledge/ — 领域知识

不可变的领域规则，为 Agent 决策提供依据。

## 内容

（本目录存放领域知识规则。NPU 硬件规格现已迁移至 `config.json`
的 `static.npu_specs` 字段中。）

## 原则

- 本目录中的文件是**只读参考**——禁止基于单次运行修改
- 新的领域知识（算子限制、显存分配策略等）添加于此，而非 skill 本地 references
- NPU 硬件规格：读取 `config.json` → `static.npu_specs`
- 代码风格规约：参见 `reference/code-style/`
- 接口契约：参见 `reference/io_specs/`