# 性能对比报告格式规范

## 基本要求

- 报告必须使用中文撰写
- 所有性能指标必须包含 avg、p50、p90、p99 四个维度
- 指标列表：TTFT、TPOT、ITL、Output throughput、Total throughput

## 报告结构

### 1. 分并发独立报告

为每个并发场景（parallel=1/2/4）分别生成独立的对比报告，
存放路径：`<artifact_root>/parallel_{parallel}/comparison/report.md`

每个报告包含：
- 环境信息表（容器名、镜像、框架版本、CANN 版本、端口）
- 配置一致性检查表
- 完整性能对比表（avg + p50 + p90 + p99）
- 差异分析和胜出方标注
- 结论

### 2. 总报告

生成一份总报告，汇总所有并发场景的完整对比分析，
存放路径：`<artifact_root>/report.md`

总报告包含：
- 环境信息表
- 配置一致性检查表
- 按指标分类的完整对比表（TTFT、TPOT、吞吐量各自独立表格）
  - 每个表格包含所有并发场景的 avg、p50、p90、p99
- 趋势图（ASCII 柱状图）
- 综合对比汇总（xLLM 胜出项 / vLLM 胜出项）
- 扩展性分析
- 最终结论

### 3. 增量模式报告标注

incremental 模式下，报告中必须明确标注：
- xLLM 为本次新跑结果
- vLLM-Ascend 为历史基线结果
- 引用 vLLM 历史结果来源路径

## 对比表模板

```markdown
| 并发 | 指标 | xLLM | vLLM-Ascend | 差异 | 胜出 |
|------|------|------|-------------|------|------|
| 1 | avg | xxx | xxx | -x.x% | xLLM |
| 1 | p50 | xxx | xxx | -x.x% | xLLM |
| 1 | p90 | xxx | xxx | -x.x% | xLLM |
| 1 | p99 | xxx | xxx | -x.x% | xLLM |
```

差异列说明：
- 延迟指标（TTFT、TPOT）：负值表示 xLLM 更优，正值表示 vLLM 更优
- 吞吐指标：负值表示 xLLM 较低，正值表示 xLLM 较高
