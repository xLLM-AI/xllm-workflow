# scripts/ — 确定性引擎

编译、启动服务、性能测试、精度测试等自动化脚本库。
这些脚本是**确定性**的——LLM 不得修改脚本逻辑，变更需人工审核。

## 内容

- `query.py` — 查询 `reference/pr_history/` 中的模型 dossier（按模型、关键词、路径过滤）
- `init_xllm_workspace.py` — 初始化 `code/xllm`，从 `config.example.json` 生成本地 `config.json`，读取或补齐 xLLM 仓库信息，并按启动方式链接 skills
- `collect_evalscope_results.py` — 收集并标准化 evalscope 评测结果
- `compare_npu_benchmark.py` — 跨框架 NPU 性能对比
- `validate_framework_cli.py` — 验证框架 CLI 参数合法性

## 原则

- 本目录脚本为跨 skill 共用工具；skill 专属脚本保留在各 skill 的 `scripts/` 子目录
- 所有脚本必须能在仓库根目录下直接运行
- 参数变更写入本地 `config.json`，不在脚本中硬编码；共享默认值写入 `config.example.json`

## 初始化 xLLM 代码仓和 Skills

方式 1：在本项目根目录启动 code agent。脚本会初始化 `code/xllm`，并把本项目
`skills/*` 与 xLLM 仓内 skills 链接到生成目录 `.agents/skills`：

```bash
python scripts/init_xllm_workspace.py
```

方式 2：在 `code/xllm` 下启动 code agent。脚本会初始化 `code/xllm`，并把本项目
`skills/*` 链接到所选 agent 的 skills 目录：

```bash
python scripts/init_xllm_workspace.py --mode xllm --agent codex
# 或兼容快捷参数
python scripts/init_xllm_workspace.py --install-project-skills --agent codex
```

如果 `config.json` 不存在，脚本会先从 `config.example.json` 生成本地文件。如果本地 `config.json` 中还没有 xLLM 仓库配置，脚本会交互式询问仓库 URL、分支或 commit，并写回：

```json
{
  "code": {
    "xllm": {
      "path": "code/xllm",
      "origin": {
        "url": "<your-fork-or-origin-url>",
        "branch": "<branch>",
        "commit": ""
      },
      "upstream": {
        "url": "https://github.com/jd-opensource/xllm.git",
        "branch": "main",
        "commit": ""
      }
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

脚本只会在 `code/xllm` 不存在或为空时拉取代码；如果目录已存在，会跳过 clone。
