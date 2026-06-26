# reference/knowledge/ — 领域知识

不可变的领域规则，为 Agent 决策提供依据。

## 内容

(本目录存放领域知识规则. NPU 硬件规格, 官方资料和测量口径等
静态参考信息也放在这里.)

## 文件

- `npu-hardware-specs.json`: NPU 硬件规格静态参考, 由原 `config.example.json` 中的硬件信息迁移而来

## 原则

- 本目录中的文件是**只读参考**——禁止基于单次运行修改
- 新的领域知识（算子限制、显存分配策略等）添加于此，而非 skill 本地 references
- NPU 硬件规格: 参见 `npu-hardware-specs.json`, 并结合实际机器证据校准
