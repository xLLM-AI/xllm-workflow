---
name: xllm-npu-report-writer
description: xLLM NPU 评测报告生成器。汇总 run root 下的性能、精度、环境 artifacts，按调用方提供的模板生成结构化 report.md。可独立使用，也可被其他 skill 委托调用。
---

# xLLM NPU 评测报告生成器

汇总 run root 下的所有 artifacts，按调用方指定的模板生成结构化报告。

## 职责边界

- 本 skill：读取 artifacts、读取模板、汇总指标、生成 report.md。
- **不拥有**报告模板。模板由各调用方 skill 自行维护。
- 调用方：`xllm-npu-benchmark`（A/B 对比报告）、`xllm-npu-batch-perf`（批量性能汇总报告）、`xllm-npu-eval-runner`（端到端评测报告）。

## 输入

| 参数 | 说明 | 必填 | 示例 |
|---|---|---|---|
| Run Root | 产物根目录 | 是 | `runs/eval/20260622_xllm_npu_eval` |
| template_path | 报告模板文件路径（调用方 skill 的 references 下） | 是 | `skills/xllm-npu-benchmark/references/report-template.md` |
| report_type | 报告类型标识（写入报告元信息） | 否 | `benchmark` / `batch-perf` / `eval` |

### 调用方模板约定

每个调用方 skill 在自己的 `references/` 目录下维护报告模板：

| 调用方 skill | 模板路径 | 说明 |
|---|---|---|
| `xllm-npu-benchmark` | `references/report-template.md` | A/B 对比报告（总报告 + 分并发报告） |
| `xllm-npu-batch-perf` | `references/summary-template.md` | 批量性能汇总报告 |
| `xllm-npu-eval-runner` | `references/report-template.md` | 端到端评测报告（如有） |
| 其他 skill | `references/*-template.md` | 按需添加 |

**模板所有权**：模板文件归调用方 skill 所有，report-writer 只读取不修改。
如需调整报告格式，修改对应调用方 skill 的模板文件。

## 工作流

### Step 1: 读取模板

从 `template_path` 读取报告模板，解析其结构（章节标题、表格占位符、必填字段）。
模板中使用 `{占位符}` 标记需要填充的数据位置。

### Step 2: 读取 artifacts

从 `$RUN_ROOT` 读取：

- `manifest.md` — run 元信息
- `env/` — 环境快照（npu-smi、进程表、内存、负载）
- `perf/metrics.json` — 性能指标
- `perf/` — evalscope 原始输出（`benchmark_summary.json`、`benchmark_percentile.json`）
- `accuracy/` — 精度评测结果

### Step 3: 填充模板并生成报告

将 artifacts 数据填入模板占位符，写出报告文件。

报告输出路径由模板定义，常见约定：
- 总报告：`$RUN_ROOT/report.md`
- 分并发报告：`$RUN_ROOT/parallel_{P}/comparison/report.md`
- 批量汇总：`$BATCH_ROOT/summary.md`

### Step 4: 可选 Baseline 对比

从 GitHub 获取 baseline 数据（如有）：

```
BENCHMARK_URL=https://raw.githubusercontent.com/jd-opensource/xllm/main/docs/benchmark/baseline.md
```

构建对比表：

```
| Metric | Current | Baseline | Delta | Status |
|---|---|---|---|---|
| Output Throughput (tok/s) | XX.XX | XX.XX | +X.X% | PASS/FAIL |
| TTFT (ms) | XXXX | XXXX | -X.X% | PASS/FAIL |
| TPOT (ms) | XX.XX | XX.XX | +X.X% | PASS/FAIL |
```

状态规则：
- **Performance metrics**：current >= baseline * 0.95 判定 PASS，容忍 5%。
- **Latency metrics**：current <= baseline * 1.05 判定 PASS，容忍 5%。
- **Accuracy metrics**：current >= baseline - 0.02 判定 PASS，容忍 2 个百分点。

## 调用方委托协议

### 协议规则

1. 调用方 skill 在需要生成报告时，加载本 skill（`xllm-npu-report-writer`）。
2. 调用方传入 `template_path` 指向自己的模板文件。
3. 本 skill 读取模板、读取 artifacts、填充数据、写出报告。
4. 本 skill **不修改**调用方的模板文件。

### 调用示例

#### 从 xllm-npu-benchmark 调用

```
加载 xllm-npu-report-writer，参数：
  Run Root: /export/home/weinan5/wanghao/runs/20260625_bench_35b
  template_path: skills/xllm-npu-benchmark/references/report-template.md
  report_type: benchmark
```

#### 从 xllm-npu-batch-perf 调用

```
加载 xllm-npu-report-writer，参数：
  Run Root: /export/home/weinan5/wanghao/batch_runs/multi_model_perf_20260623
  template_path: skills/xllm-npu-batch-perf/references/summary-template.md
  report_type: batch-perf
```

#### 独立使用

```
加载 xllm-npu-report-writer，参数：
  Run Root: runs/eval/20260622_xllm_npu_eval
  template_path: skills/xllm-npu-benchmark/references/report-template.md
```

### 新增调用方

如果新的 skill 需要使用 report-writer：

1. 在新 skill 的 `references/` 下创建自己的报告模板（`*-template.md`）。
2. 在新 skill 的 SKILL.md 中声明模板路径和调用方式。
3. 在上表"调用方模板约定"中登记。

## 中文报告生成方法（关键）

### 问题

从 Windows 宿主机通过 SSH 管道向远程容器写入包含中文的 Markdown 文件时，
中文字符会丢失（变成 `?` 乱码）。原因是 Windows OpenSSH 管道默认使用系统编码（GBK），
而远程容器期望 UTF-8，编码不匹配导致中文被替换。

### 解决方案：Python unicode escape

**不要**使用 shell heredoc（`cat << 'EOF'`）或 `echo` 直接写入中文内容。
改用 Python 脚本，将所有中文写成 unicode escape 序列（`\uXXXX`），
Python 解释器在远程容器内执行时自动还原为 UTF-8 中文。

#### 步骤

1. 在本地编写 Python 脚本，报告内容用 Python 字符串表示，中文字符使用 `\uXXXX` 转义。
2. 通过管道将脚本上传到远程容器：
   ```powershell
   Get-Content "local_script.py" -Raw | ssh <host> "docker exec -i -u root <container> bash -c 'cat > /tmp/gen_report.py && python3 /tmp/gen_report.py'"
   ```
3. Python 脚本在容器内执行，直接以 UTF-8 写入文件，中文完整保留。

#### 示例

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os

RUN_ROOT = "/export/home/weinan5/wanghao/runs/20260625_bench_35b"

def write_report(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

# 中文使用 \uXXXX 转义，Python 执行时自动还原
report = """# Qwen3.5-35B-A3B \u6027\u80fd\u5bf9\u6bd4\u62a5\u544a

## \u6d4b\u8bd5\u6982\u8981

- **\u6d4b\u8bd5\u65e5\u671f**: 2026-06-25
- **\u6a21\u578b**: Qwen3.5-35B-A3B
"""

write_report(f"{RUN_ROOT}/report.md", report)
```

#### 常用中文 unicode escape 速查

| 中文 | unicode |
|------|---------|
| 性能对比总报告 | `\u6027\u80fd\u5bf9\u6bd4\u603b\u62a5\u544a` |
| 测试概要 | `\u6d4b\u8bd5\u6982\u8981` |
| 测试日期 | `\u6d4b\u8bd5\u65e5\u671f` |
| 运行模式 | `\u8fd0\u884c\u6a21\u5f0f` |
| 模型 | `\u6a21\u578b` |
| 并发数 | `\u5e76\u53d1\u6570` |
| 请求数 | `\u8bf7\u6c42\u6570` |
| 采样参数 | `\u91c7\u6837\u53c2\u6570` |
| 环境信息 | `\u73af\u5883\u4fe1\u606f` |
| 容器 | `\u5bb9\u5668` |
| 端口 | `\u7aef\u53e3` |
| 模型名 | `\u6a21\u578b\u540d` |
| 配置一致性检查 | `\u914d\u7f6e\u4e00\u81f4\u6027\u68c0\u67e5` |
| 一致性 | `\u4e00\u81f4\u6027` |
| 说明 | `\u8bf4\u660e` |
| 对比 | `\u5bf9\u6bd4` |
| 指标 | `\u6307\u6807` |
| 差异 | `\u5dee\u5f02` |
| 胜出 | `\u80dc\u51fa` |
| 吞吐量对比 | `\u541e\u5410\u91cf\u5bf9\u6bd4` |
| 输出吞吐量 | `\u8f93\u51fa\u541e\u5410\u91cf` |
| 总吞吐量 | `\u603b\u541e\u5410\u91cf` |
| 请求吞吐量 | `\u8bf7\u6c42\u541e\u5410\u91cf` |
| 效率对比 | `\u6548\u7387\u5bf9\u6bd4` |
| 扩展性分析 | `\u6269\u5c55\u6027\u5206\u6790` |
| 吞吐量随并发变化 | `\u541e\u5410\u91cf\u968f\u5e76\u53d1\u53d8\u5316` |
| 随并发变化趋势 | `\u968f\u5e76\u53d1\u53d8\u5316\u8d8b\u52bf` |
| 综合对比汇总 | `\u7efc\u5408\u5bf9\u6bd4\u6c47\u603b` |
| 胜出项 | `\u80dc\u51fa\u9879` |
| 公平性门禁 | `\u516c\u5e73\u6027\u95e8\u7981` |
| 同一 | `\u540c\u4e00` |
| 模型权重 | `\u6a21\u578b\u6743\u91cd` |
| 设备 | `\u8bbe\u5907` |
| 内存利用率 | `\u5185\u5b58\u5229\u7528\u7387` |
| 请求级 | `\u8bf7\u6c42\u7ea7` |
| 环境门禁 | `\u73af\u5883\u95e8\u7981` |
| 空闲 | `\u7a7a\u95f2` |
| 最终结论 | `\u6700\u7ec8\u7ed3\u8bba` |
| 全面优于 | `\u5168\u9762\u4f18\u4e8e` |
| 具体表现 | `\u5177\u4f53\u8868\u73b0` |
| 首 Token 延迟 | `\u9996 Token \u5ef6\u8fdf` |
| 每 Token 延迟 | `\u6bcf Token \u5ef6\u8fdf` |
| 平均快 | `\u5e73\u5747\u5feb` |
| 高并发下 | `\u9ad8\u5e76\u53d1\u4e0b` |
| 优势更大 | `\u4f18\u52bf\u66f4\u5927` |
| 最高 | `\u6700\u9ad8` |
| 低并发优势更明显 | `\u4f4e\u5e76\u53d1\u4f18\u52bf\u66f4\u660e\u663e` |
| 低并发时优势最大 | `\u4f4e\u5e76\u53d1\u65f6\u4f18\u52bf\u6700\u5927` |
| 两者 | `\u4e24\u8005` |
| 接近 | `\u63a5\u8fd1` |
| 略低但 | `\u7565\u4f4e\u4f46` |
| 更优 | `\u66f4\u4f18` |
| 基础推理效率更高 | `\u57fa\u7840\u63a8\u7406\u6548\u7387\u66f4\u9ad8` |
| 结果等级 | `\u7ed3\u679c\u7b49\u7ea7` |
| 可作为正式结论写入 | `\u53ef\u4f5c\u4e3a\u6b63\u5f0f\u7ed3\u8bba\u5199\u5165` |
| 产物路径 | `\u4ea7\u7269\u8def\u5f84` |
| 分并发报告 | `\u5206\u5e76\u53d1\u62a5\u544a` |
| 总报告 | `\u603b\u62a5\u544a` |
| 原始结果 | `\u539f\u59cb\u7ed3\u679c` |
| 服务日志 | `\u670d\u52a1\u65e5\u5fd7` |
| 温度 | `\u6e29\u5ea6` |
| 内存 | `\u5185\u5b58` |
| 单卡 | `\u5355\u5361` |
| 两个框架均为本次新跑结果 | `\u4e24\u4e2a\u6846\u67b6\u5747\u4e3a\u672c\u6b21\u65b0\u8dd1\u7ed3\u679c` |
| 项目 | `\u9879\u76ee` |
| 模式 | `\u6a21\u5f0f` |
| 物理卡 | `\u7269\u7406\u5361` |
| 结论 | `\u7ed3\u8bba` |
| 场景下 | `\u573a\u666f\u4e0b` |
| 批量性能汇总 | `\u6279\u91cf\u6027\u80fd\u6c47\u603b` |
| 配置表 | `\u914d\u7f6e\u8868` |
| 性能对比表 | `\u6027\u80fd\u5bf9\u6bd4\u8868` |
| 关键发现 | `\u5173\u952e\u53d1\u73b0` |
| 备注 | `\u5907\u6ce8` |
| 汇总 | `\u6c47\u603b` |

#### 不推荐的方法

| 方法 | 问题 |
|------|------|
| shell heredoc (`cat << 'EOF'`) | Windows SSH 管道 GBK→UTF-8 编码不匹配，中文变 `?` |
| `echo "中文"` | 同上 |
| base64 编码传输 | Windows PowerShell 的 `Get-Content -Raw` 输出带 `\r\n`，`base64 -d` 报 invalid input |
| scp/sftp 直传 | 需要额外认证配置，不如管道方便 |

## 输出

报告文件路径由调用方模板定义，常见：

```
$RUN_ROOT/report.md                              # 单模型/对比报告
$RUN_ROOT/parallel_{P}/comparison/report.md       # 分并发报告
$BATCH_ROOT/summary.md                            # 批量汇总
```

报告需要说明执行了什么、原始 artifacts 存在哪里，以及本次 run 是否足够支撑正式结论。
如果只是 smoke run，必须明确说明。
