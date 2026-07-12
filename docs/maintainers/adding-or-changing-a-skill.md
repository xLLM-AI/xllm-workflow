# 新增或修改 Skill

使用以下流程保持 canonical discovery、routing ownership、生成文档与安装链接一致。

## 1. 判断使用 Skill 还是脚本

需要复用过程化判断、排序或委托时使用 skill；确定性执行与验证放入 `scripts/` 或 skill-local script。不要为内部 evidence validator、checksum、projection、fairness function 或 Big-Rock 实现细节新增 public skill。

## 2. 定义合约

选择稳定 canonical ID 与扁平目录 `skills/<canonical-id>/`。在 `SKILL.md` 中定义 `name` 与 routing `description`，并确定 category、human role、domain、visibility、primary/negative intents、dependencies、lifecycle/framework/backend scopes 与用户可见 outputs。

不要创建 `skills/00-orchestration/` 等物理分类目录。只有真实 rename 需要兼容时才创建 alias，且必须直接指向一个 canonical target。

## 3. 新增或更新 `SKILL.md`

保持流程简洁，把详细材料放入 `references/`。除非单独审查 routing 变化，否则不得修改既有 ID 或 description。仅显式调用的 internal skill 必须保留 `agents/openai.yaml`，并关闭 implicit invocation。

## 4. 更新 Catalog

编辑 `skills/catalog.json`。Routing 字段负责机器可读 taxonomy 与 discovery；`presentation` 只负责人类显示名称、角色、领域、暴露方式、摘要、outputs 与 featured 状态。Presentation metadata 不得改变 routing 行为。

立即验证：

```bash
python scripts/validate_skill_catalog.py
```

## 5. 更新 Routing Cases

新增 public outcome 或修改 routing semantics 时，更新 `tests/routing/cases.json` 与 `tests/test_skill_routing.py`。不得为了掩盖 observed mismatch 修改 `expected_primary`；internal skill 不能成为 expected primary。

## 6. 生成文档

不得手工编辑以下生成文件：

- `skills/README.md`
- `docs/architecture/skill-map.md`

重新生成并检查：

```bash
python scripts/render_skill_docs.py
python scripts/render_skill_docs.py --check
```

根 `README.md`、`README_zh.md`、`docs/README.md` 与架构说明由人工维护。只有公开概念或导航发生变化时，才同步更新两份根 README 与 `AGENTS.md`。

## 7. Refresh 已安装 Skills

按 agent 启动位置选择：

| Agent 启动位置 | Refresh 命令 |
|---|---|
| 当前 workflow 仓库 | `python scripts/init_xllm_workspace.py` |
| xLLM checkout | `python scripts/init_xllm_workspace.py --mode xllm --agent codex` |

确认所有 canonical entry 均已安装，没有真实目录被意外 skip，也没有断链。验证 injected metadata 时，应在 refresh 后启动新 task。

## 8. 验证与 Probe

```bash
python scripts/validate_skill_catalog.py
python scripts/render_skill_docs.py --check
pytest -q
git diff --check
```

确认 installer 集合与 catalog 一致、baseline names 仍可解析且没有 orphan `SKILL.md`。只有 routing semantics 改变时才运行 fresh-task routing probe；纯文档导航变化使用 bounded reader probe。

## 支持与兼容规则

- xLLM on Ascend 是完整主工作流。
- vLLM-Ascend 与 SGLang 仅限已声明的 experimental adapter 或 artifact-analysis scope。
- 不得从 build adapter 或可分析 artifact 推导完整框架支持。
- 除非经过单独批准的迁移，否则保持既有 canonical ID、路径与显式调用行为。
