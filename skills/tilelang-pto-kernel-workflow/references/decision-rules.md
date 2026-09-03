# Decision Rules

## 目录

1. Plan 三态
2. 何时复采
3. 互斥与叠加
4. 派生规则
5. 切换到 PTO
6. 停止条件
7. 经验回填

## 1. Plan 三态

### 通过

必须同时满足：

- candidate 路径真实命中；
- Golden、state 和要求的生产精度门禁通过；
- source/Profile 证明目标机制发生变化；
- 性能超过测量噪声并达到 Plan 验收线；
- 非主 Shape 没有无法解释的明显回退；
- 回退方式可用；
- 与已通过 Plan、互斥组状态一致。

通过后 candidate 才能成为下一轮 baseline。

### 淘汰

任一条件成立即可：

- 编译、精度、稳定性、资源或 Graph 失败；
- candidate 路径未命中；
- 无收益、收益低于噪声且没有新的证据；
- 引入多余 layout/GM、资源暴涨或其他副作用；
- 跨 Shape 结果不稳定且无法按业务分派；
- 与更强的同组 Plan 互斥；
- 参数变化只改变偶然环境状态。

记录淘汰证据、代码/开关是否已回退，以及是否派生新 Plan。不要删除失败实验。

### 待实现

用于尚未实施，或 Reviewer 判断方向仍成立但缺少可补证据的 Plan。证据不足时追加新 round，不得标记通过。

## 2. 何时复采

必须复采：

- task map、owner、Core 数、Tile、stages 变化；
- dtype、layout、memory scope、Buffer 生命周期变化；
- barrier、flag/event、Double Buffer 或下发时序变化；
- intrinsic、Reduce/Broadcast、FixPipe 或 source specialization 变化；
- 切换优化方向或出现瓶颈转移；
- 要对 Plan 做通过/淘汰终裁；
- 最终验收前。

可以沿用：

- 只改测试开关、路径记录或注释；
- candidate 未改变设备代码和执行结构；
- 精度专项修复尚未进入性能终裁。

沿用 Profile 时必须在 Plan 中说明原因。

## 3. 互斥与叠加

- 同一互斥组最终只保留一个通过 Plan。
- 新 Plan 替代旧 Plan 时，旧 Plan 标记淘汰，原因写明替代者。
- 可叠加不代表收益可线性相加。
- 每种组合分配独立 round，重新跑精度、source audit、Profile 与 A/B。
- 组合退化时保留机制证据更清楚、收益更稳定的一项。

常见互斥：

- 不同 owner/task map；
- 完整 state 驻留与 half-state 分块；
- 相同 Reduce 的通用路径与专用 intrinsic；
- 不同 Base Tile/Core 映射。

常见可叠加但需实测：

- 删除中间 GM + 缩小同步范围；
- UB 复用 + 专用 Vector helper；
- source specialization + Host dispatch/fallback。

## 4. 派生规则

追加新 Plan，不改写旧 Plan：

- 原假设被推翻，但证据指向新原因；
- 参数方向成立，需要独立测试另一档；
- 主瓶颈从 Memory 转到 Vector/Scalar/Sync；
- 删除通用 op 后出现新的 event 或资源瓶颈；
- Reviewer 发现收益存在，但实现可缩小改动面；
- 某 Shape 需要独立 variant/fallback。

记录 `derived-from Plan-X/roundN`、触发现象、新旧差异、独立验收口径。

## 5. 切换到 PTO

同时满足以下条件再下沉：

- TileLang 公式、dtype、state 副作用和 task map 已稳定；
- TileLang 单变量 round 已完成可表达的 schedule 优化；
- generated source 与目标 SoC Profile 都指向更低层瓶颈；
- 下一步需要控制 PTO intrinsic、UB 地址、layout 或 event；
- TileLang kernel family 仍能作为 JIT/AOT 和 specialization 的生成入口。

不要只因为“PTO 更底层”就切换。若问题仍来自公式、owner、Tile 生命周期或错误 task map，先留在 TileLang。

## 6. 停止条件

满足全部条件时收尾：

- 所有 Plan 已通过或淘汰；
- 再无由当前 Profile 支持的新 Plan；
- 连续若干轮只出现噪声、单 Shape 偶然收益或其他 Shape 回退；
- 最终代码已同口径复采；
- kernel、生产框架、模型和精度门禁已完成，或未完成项明确写入风险。

性能目标未达到但没有新证据时也应停止，保存最好版本。不要围绕同一代码无依据重写。

## 7. 经验回填

值得回填：

- 新的可复用优化模式；
- 新的 bound/指标映射；
- 现有模式的新适用边界；
- 新算子 state/owner/task-map 档案；
- 有普遍价值的失败案例。

每条必须包含来源算子与 Shape 类别、SoC/CANN、Profile 指标变化、性能结果、精度结论、限制和目标参考文件。只生成草案；审阅后再写回。
