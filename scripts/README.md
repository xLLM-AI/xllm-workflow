# scripts/ — 确定性引擎

编译、启动服务、性能测试、精度测试等自动化脚本库。
这些脚本是**确定性**的——LLM 不得修改脚本逻辑，变更需人工审核。

## 内容

- `query.py` — 查询 `reference/pr_history/` 中的模型 dossier（按模型、关键词、路径过滤）
- `init_xllm_workspace.py` — 初始化 `code/xllm`，从 `config.json` 读取或补齐 xLLM 仓库信息，拉取代码并把 xLLM skills 链接到 `.agents/skills`
- `collect_evalscope_results.py` — 收集并标准化 evalscope 评测结果
- `compare_npu_benchmark.py` — 跨框架 NPU 性能对比
- `validate_framework_cli.py` — 验证框架 CLI 参数合法性

## 原则

- 本目录脚本为跨 skill 共用工具；skill 专属脚本保留在各 skill 的 `scripts/` 子目录
- 所有脚本必须能在仓库根目录下直接运行
- 参数变更写入 `config.json`，不在脚本中硬编码

## 初始化 xLLM 代码仓

首次准备本地 xLLM 开发目录：

```bash
python scripts/init_xllm_workspace.py
```

如果 `config.json` 中还没有 xLLM 仓库配置，脚本会交互式询问仓库 URL、分支或 commit，并写回：

```json
{
  "repositories": {
    "xllm": {
      "url": "<git-url>",
      "ref": "<branch-or-commit>",
      "ref_type": "branch"
    }
  }
}
```

非交互场景可直接传参：

```bash
python scripts/init_xllm_workspace.py \
  --repo-url <git-url> \
  --ref <branch-or-commit> \
  --ref-type branch
```

脚本只会在 `code/xllm` 不存在或为空时拉取代码；如果目录已存在，会跳过 clone，并继续链接 `code/xllm/.agents/skills` 或 `code/xllm/skills` 中的 skills。
