---
name: model-pr-optimization-history
description: 查询 xLLM 历史 PR 中的优化信息，辅助当前模型的优化决策。
---

# 模型 PR 优化历史

通过查询本地模型档案和历史 PR 经验，获取模型相关的优化、风险和验证记录，
避免重复工作。该 skill 是 evidence loop 中的 Learn 阶段入口。

## 使用场景

1. 开始优化某模型前，先查询历史 PR 中的已知优化
2. 遇到特定性能问题时，搜索历史 PR 中的解决方案
3. 了解 xLLM 对该模型的支持状态

## 工作流

### Step 1: 查询历史经验

使用 `scripts/query.py` 查询模型档案：

```bash
# 按模型查询
python model-pr-optimization-history/scripts/query.py --model Qwen3.5

# 按关键词查询
python model-pr-optimization-history/scripts/query.py --keyword mtp --keyword graph

# 按框架和代码路径查询
python model-pr-optimization-history/scripts/query.py \
    --framework xllm \
    --path MTPWorkerImpl::run_validate \
    --verbose
```

### Step 2: 整理优化历史

将查询结果整理为模型档案，存入 `<framework>/<model>.md`。字段参考
`references/card-schema.md`：

```markdown
## Case: <short title>

- intent:
- touched_paths:
- validation:
- risks:
- next_checks:
```

### Step 3: 识别未覆盖优化

对比当前工作负载与历史优化，找出：
1. **已实现的优化**：无需重复实现
2. **部分实现的优化**：需要进一步完善
3. **未实现的优化**：新的优化机会

## 查询输出字段

| 字段 | 说明 |
|------|------|
| framework | 框架目录 |
| model | 档案文件名 |
| path | 档案相对路径 |
| match_count | 查询词命中数量 |
| sections | 命中的相关章节 |

## 模型档案目录

- `model-pr-optimization-history/xllm/deepseek-v3.md` — DeepSeek-V3 (MoE)
- `model-pr-optimization-history/xllm/qwen35-mtp.md` — Qwen3.5 / Qwen3 Next / Qwen3.6 / MTP / graph / VLM / PD
- `model-pr-optimization-history/xllm/glm-5.md` — GLM-5 系列

## 维护

模型档案应随新 PR 合并而更新。建议：
- 每次框架新 PR 合并后，检查是否影响已归档的模型
- 季度审查一次档案的准确性
- 对 MTP、graph、sampling、KV cache、VLM、MoE 等风险路径优先沉淀 case
