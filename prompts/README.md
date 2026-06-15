# Prompts

本目录保存可直接复制给 Codex、Claude Code、opencode 或其他 coding agent 的
中文任务入口模板。

Prompt 的定位是“启动一轮具体工作”；Skill 的定位是“定义执行步骤、证据契约和
验证门禁”。使用时先复制一个 prompt，补齐尖括号里的字段，再让 agent 按提示加载
对应 skill。

## Prompt 索引

| 文件 | 适用场景 |
|---|---|
| [`xllm-npu-sota-loop-prompts.md`](xllm-npu-sota-loop-prompts.md) | 端到端 SOTA 优化、TPOT/TTFT/TPS 目标优化、MTP 接受率验证、decode 空泡分析 |
| [`xllm-npu-eval-profiler-prompts.md`](xllm-npu-eval-profiler-prompts.md) | 服务启动、evalscope 性能/精度评测、profiling 采集、容量/OOM 分析 |
| [`xllm-npu-pr-fix-prompts.md`](xllm-npu-pr-fix-prompts.md) | PR 精度/性能/事故回归修复、review 回复、rebase、编译和 UT 门禁 |
| [`xllm-npu-operator-work-prompts.md`](xllm-npu-operator-work-prompts.md) | NPU 算子工作、Triton-Ascend AOT 迁移、xllm_ops runtime 接入、kernel-pilot 准入 |

## 使用规则

1. 补齐模型、硬件、框架 commit、workload、采样参数、artifact root。
2. 性能任务必须显式要求 warmup，并区分正式性能 run 和 profiling run。
3. 精度任务先建立最小稳定坏例，再逐步升级到数据集子集和全量 task。
4. 代码任务每轮只做一个可验证 patch，先验证再扩大优化范围。
5. 每个 prompt 结尾都要要求沉淀经验：run ledger、reference、
   skill 或 model PR history。

## 推荐启动方式

```text
请使用 <skill-name>，按下面任务模板执行。
如果信息缺失，先从当前仓库、脚本、日志和 manifest 中查找；仍然缺失时再一次性向我确认。
不要在没有 baseline/profiling/精度验证的情况下修改代码或给出性能结论。
```
