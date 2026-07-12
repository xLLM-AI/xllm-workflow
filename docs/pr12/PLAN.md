# PR #12：重构 workflow skill taxonomy 与 routing

## Codex 执行入口

将本 Issue 作为本次任务的**单一设计与验收来源**。在最新 `main` 上创建独立分支，按本文所有阶段依次完成；不要依赖此前聊天记录猜测设计。

建议分支：

```text
refactor/skill-taxonomy-routing
```

开始前必须：

1. 读取仓库内所有适用的 `AGENTS.md`。
2. 更新本地 `main`，确认 PR #11 已进入基线。
3. 记录 `HEAD`、dirty state、已注册 skill 链接和当前测试基线。
4. 使用子代理并行审计 skill inventory、routing 冲突和实现依赖；主代理负责交叉验证和最终决策。
5. 将本 Issue 内容落盘为 `docs/pr12/PLAN.md`，后续在该文件维护 Progress 与 Decision Log。
6. 在一个 Codex 任务内完成全部阶段，但按独立 commit 和检查点推进；遇到会改变公开行为或兼容性的阻塞问题时，记录为 `INCONCLUSIVE`，不得静默绕过。

---

## 背景

PR #11 已建立或强化：

- `xllm-flow` 统一实验生命周期；
- experiment manifest、preflight、attempt ledger、checkpoint、finalize、archive；
- build provenance 与 build gate；
- deterministic service lifecycle 与 cleanup evidence；
- benchmark fairness、run evidence 与 `gate all`；
- Big-Rock 性能优化门禁；
- xLLM 主路径；
- vLLM-Ascend、SGLang 实验性 build adapter；
- Ascend NPU 与 NVIDIA GPU snapshot backend。

PR #12 不再增加新的实验子系统，重点解决 skill 架构、命名和自动路由问题。

当前需要验证的假设：

1. skill 名称混用了用户意图、执行方法、workload 形态、生命周期阶段与底层机制。
2. orchestrator、runner、analyzer、gate、support skill 暴露在同一 routing 层级。
3. `sota-loop`、`eval-runner`、`benchmark`、`batch-perf` 等可能对同一个高层请求产生竞争。
4. 部分底层 gate/validator 可能不应成为普通任务的 primary skill。
5. 直接 rename/delete 会破坏旧 prompt、旧 session 和已注册软链接。
6. taxonomy 需要支持未来 framework/backend 扩展，但不得宣称尚未真实验证的端到端支持。

以上均为待验证假设，不得直接当成重构结论。

---

## 总目标

- 建立机器可读、可测试的 skill taxonomy。
- 明确 public entry 与 internal implementation 的边界。
- 为每类用户意图定义唯一 preferred primary route。
- 明确 orchestrator、planner、runner、analyzer、gate、support 的职责。
- 用 routing eval 证明 rename、merge、split 或 internalize 的收益。
- 通过 alias/redirect 保持旧名称和旧 prompt 兼容。
- 保持 PR #11 lifecycle、schema、evidence 与 gate 语义稳定。
- 不把所有能力合并成单一巨型 skill。
- 不把实验性 adapter 描述为完整 framework 支持。

### 成功标准

1. 当前所有 `skills/*/SKILL.md` 均被 inventory 覆盖。
2. 每个 skill 均有 category、visibility、primary intents、negative intents、inputs、outputs、dependencies 和 framework/backend scope。
3. routing tests 同时包含正向、负向和歧义用例。
4. 每个 rename/merge/split/internalize 决策均引用代码证据和 routing baseline。
5. public skills 的 primary responsibility 不重叠。
6. internal skills 不再成为普通用户目标的 primary route。
7. 旧名称存在清晰、无循环的兼容机制。
8. full tests、routing tests、catalog validation、skill refresh 和 smoke 全部通过。
9. PR 只包含 taxonomy/routing/兼容相关修改。

---

## 非目标

本 PR 不得：

- 重写 `xllm-flow`；
- 增加新的 build/service/fairness/evidence gate；
- 改变 benchmark、profiling 或 accuracy 语义；
- 宣称 vLLM-Ascend/SGLang 完整支持；
- 迁移历史 `runs/`；
- 在兼容证据不足时删除旧 skill；
- 为了目录整齐而进行大规模无行为收益的 move；
- 修改 xLLM runtime/performance 实现；
- 将 checksum/parser/projection 等实现细节包装成新的公开 skill。

---

## 设计原则

### 1. 最新代码是事实源

必须读取：

- 全部适用的 `AGENTS.md`；
- 每个 `skills/*/SKILL.md`；
- 对应 `scripts/`、`references/`；
- `README.md`、`README_zh.md`、scripts README、prompts 与 routing 文档；
- `scripts/xllm_flow.py` 及 facade/gate 调用点；
- skill install/refresh 脚本；
- skill、workflow、documentation 相关测试。

不要预设当前仍然只有 19 个 skill。

### 2. 先测量，再改名

只有出现以下至少一项证据时，才允许 rename/merge/split/internalize：

- trigger description 实质重叠；
- 两个 skill 总是一起出现且没有独立输入输出；
- 名称显著误导当前职责；
- 实现型组件被频繁选为 public entry；
- routing eval 显示系统性误路由；
- skill 没有独立用户意图；
- 多个 public route 实际执行同一操作但产生不同契约。

仅“命名不统一”不足以支持重构。

### 3. Public interface 与 implementation 分离

初始分类假设：

- `orchestrator`：接收完整目标并协调生命周期；
- `planner`：生成 bottleneck budget、hypothesis、candidate ranking、experiment plan；
- `runner`：执行一种明确 workload/evaluation；
- `analyzer`：解释已有证据；
- `gate`：验证状态或证据；
- `support`：report、triage、migration、maintenance；
- `internal`：parser、projection、checksum、schema validator、implementation helper。

最终分类以代码审计为准。

### 4. 兼容优先

- 第一轮不删除旧名称。
- alias/redirect 必须指向唯一 canonical implementation。
- 旧入口至少保留一个迁移周期。
- 旧 prompt 与新 prompt 都进入 routing tests。
- compatibility skill 不得与 canonical skill 竞争新任务 primary route。

### 5. 单一 metadata 来源

taxonomy、aliases 和 visibility 使用一个机器可读 catalog。必须阻止：

- canonical ID 重复；
- catalog 漏项；
- 无效 dependency；
- alias cycle；
- alias 指向不存在的 target；
- README/SKILL description/catalog 漂移。

文件名与格式应遵循仓库现有约定，不强制预设 `_catalog.yaml`。

---

# 执行阶段

## Phase 0：完整只读审计

### 产物

创建：

```text
docs/pr12/PLAN.md
docs/pr12/SKILL_INVENTORY.md
docs/pr12/CURRENT_DAG.md
docs/pr12/ROUTING_CONFLICTS.md
```

### 每个 skill 必须记录

- directory 与 declared name；
- description/trigger；
- probable category；
- inputs；
- outputs/artifacts；
- scripts/references；
- direct dependencies；
- callers/entry points；
- framework/backend scope；
- 是否适合 public entry；
- negative intents；
- overlap；
- 代码证据路径；
- preliminary disposition：keep / investigate rename / investigate merge / investigate split / internalize / compatibility。

### 必答问题

1. 是否已经存在与 `xllm-flow` lifecycle 对应的 public skill？
2. SOTA/performance loop 的真实职责是什么？
3. eval runner、performance runner、batch perf、benchmark、accuracy runner 的边界是什么？
4. profiler collection 与 pipeline analysis 是否正确分离？
5. incident triage 和 report writer 是否具有独立用户意图？
6. 哪些 build/service/fairness/evidence gate 具有合法 direct maintenance 用例？
7. parser/snapshot/checksum/projection 是 skill 还是普通实现脚本？
8. framework/backend adapter 是否需要更通用名称？
9. 哪些 description 会竞争同一高层 prompt？
10. 哪些 skill 无引用、不可达或只被内部调用？

### 门禁

- inventory 覆盖所有 skill；
- DAG 每个重要 edge 都有路径证据；
- facts、inferences、recommendations 明确分离；
- Phase 0 不修改 runtime code。

---

## Phase 1：建立 routing baseline

### 产物

优先遵循仓库现有测试布局；建议包括：

```text
tests/routing/cases.yaml
docs/pr12/ROUTING_MATRIX.md
docs/pr12/ROUTING_BASELINE.md
```

### 用例格式

```yaml
id: perf-optimize-decode
prompt: "优化 Qwen3.5 TP2 decode latency"
expected_primary:
  - <actual-orchestrator>
allowed_followups:
  - <actual-planner>
  - <actual-benchmark-runner>
forbidden_primary:
  - <internal-gate>
reason: "完整优化目标不应直接路由到底层 validator。"
```

### 至少覆盖

- 完整性能优化；
- benchmark-only；
- accuracy evaluation；
- profiler collection；
- pipeline/communication/host-bubble analysis；
- PR regression reproduction；
- build failure；
- service crash/readiness；
- evidence validation/archive；
- report generation；
- framework adapter boundary；
- internal gate/parser 不得为 primary 的负向场景。

至少 20 个，优先 30 个真实、脱敏历史任务。

### 门禁

- 每例有 expected primary、allowed followups、forbidden primary；
- 当前 baseline 如实记录；
- 不得为了通过而降低预期；
- 后续每个结构改动引用具体 failing/ambiguous case。

---

## Phase 2：加入 taxonomy/catalog，不改变行为

Catalog 至少包含：

- canonical ID；
- current directory；
- category；
- visibility：`public` / `internal` / `compatibility`；
- routing tier/priority；
- primary intents；
- negative intents；
- dependencies；
- aliases；
- lifecycle stage；
- framework/backend scope；
- ownership/maintenance area（如适用）。

### 测试

必须拒绝：

- missing skill；
- duplicate ID；
- invalid dependency；
- alias cycle；
- missing alias target；
- documentation/catalog drift。

本阶段不得 rename/move/delete。

---

## Phase 3：收敛 public entry 与 runner 职责

根据 Phase 0/1/2 证据回答并实施：

1. 是否需要 dedicated experiment lifecycle public skill？
2. 现有 SOTA loop 是否应泛化为 performance optimization loop？
3. eval/benchmark/batch-perf/performance runner 是独立能力还是名称重叠？
4. accuracy 是否保持独立 runner？
5. profiler collection 与 analysis 是否继续独立？
6. report/triage 是否保留 direct public entry？
7. 哪些 gate 需要 direct maintenance/debug route？

### 约束

- 不因命名统一而合并；
- 不隐藏 accuracy/performance 的关键差异；
- 除非协议确实独立，不使用 `batch` 这类 workload shape 作为顶层能力名；
- public surface 可以减少，但内部实现不得变成单体；
- 每个变更都必须改善 routing baseline。

---

## Phase 4：兼容 alias/redirect

要求：

- old name → exactly one canonical target；
- alias description 明确 compatibility 状态；
- alias 不竞争新任务 primary routing；
- 测试 alias loop、missing target、multiple target；
- 文档迁移周期和删除条件；
- skill refresh 后 canonical 与 compatibility 链接均符合预期；
- 不复制 scripts/references 形成两套实现。

---

## Phase 5：internalize 实现型 skill

仅当审计证明无独立用户意图时，将低层 validator/parser/projection/checksum helper 标为 internal。

### 约束

- 保留合理的 direct maintenance/debug CLI；
- 保留独立单元测试与可审计性；
- 确认 `xllm-flow` 或 facade 仍调用全部必要 gate；
- 不因名字含 `gate` 就自动 internalize。

---

## Phase 6：最终验证与 PR

### 必须执行

- full repository tests；
- routing eval；
- catalog/schema validation；
- skill install/link refresh；
- broken symlink check；
- old-name compatibility smoke；
- canonical-entry smoke；
- `git diff --check`；
- README / README_zh / AGENTS 一致性；
- 无 NPU synthetic lifecycle smoke；
- 条件允许时执行一个真实 xLLM NPU quick task，仅验证 routing/lifecycle，不扩展本 PR 范围。

### PR 范围

只允许：

- skill audit artifacts；
- taxonomy/catalog；
- routing tests；
- public-entry clarification；
- compatibility alias；
- internalization；
- 相关文档与安装刷新逻辑。

建议 PR 标题：

```text
refactor: improve workflow skill taxonomy and routing.
```

---

## 建议 commit 拆分

按实际 review boundary 调整，但不要压成一个大提交：

```text
docs: audit workflow skill responsibilities.
test: add workflow skill routing baseline.
refactor: add workflow skill taxonomy metadata.
refactor: clarify public workflow entry points.
refactor: add compatible skill aliases.
refactor: internalize workflow implementation skills.
docs: document workflow skill migration.
```

每个 commit message 遵循仓库规范并以句点结尾。

---

## 风险与回滚

### 风险

- description 变化造成隐性 routing regression；
- alias 与 canonical 竞争；
- catalog 与 `SKILL.md` 漂移；
- directory move 破坏已注册软链接；
- 旧 session 依赖旧名称；
- 过度收敛 public surface，损失维护场景；
- taxonomy 继续写死 xLLM/Ascend 假设。

### 回滚

- 每阶段、每 commit 独立可回滚；
- 第一轮保留原目录；
- routing baseline 作为回滚依据；
- refresh 前保存 skill-link inventory；
- 遇到行为回归，优先恢复旧 visibility/description，不删除 audit/tests。

---

## Codex 状态维护要求

在 `docs/pr12/PLAN.md` 维护：

### Progress

```text
[ ] Phase 0 audit
[ ] Phase 1 routing baseline
[ ] Phase 2 taxonomy/catalog
[ ] Phase 3 public entry/runner refactor
[ ] Phase 4 compatibility aliases
[ ] Phase 5 internalization
[ ] Phase 6 validation and PR
```

### Decision Log

每个架构决策记录：

- decision ID；
- evidence；
- alternatives considered；
- chosen option；
- compatibility impact；
- rollback method。

每阶段结束后：

1. 更新 `PLAN.md` Progress 和 Decision Log；
2. 在本 Issue 添加阶段总结，包括 commit、tests、diff scope、remaining risks；
3. 若无 blocker 自动进入下一阶段；
4. 若存在会改变公开行为且设计未覆盖的 blocker，停止并在 Issue 中明确提问，不得自行扩大范围。

---

## Definition of Done

- [x] 所有当前 skill 均完成 inventory 与 taxonomy。
- [x] routing baseline 与最终结果可比较，且主要歧义得到改善。
- [x] public/internal/compatibility 边界明确。
- [x] canonical/alias 无循环、无重复实现、无断链。
- [x] PR #11 lifecycle 与 evidence 语义无回归。
- [x] xLLM 主路径通过完整测试与 smoke。
- [x] vLLM-Ascend/SGLang 仍明确标为实验性 adapter，未过度宣称。
- [x] 文档、catalog、SKILL descriptions 与安装链接一致。
- [x] review-fix 后的 full tests、routing tests、refresh、smoke、diff check 全部通过。
- [x] 在全新 Codex task 中完成真实 routing dogfood，并记录 observed route 与 specification 的差异。
- [x] 创建 Draft PR，标题符合规范并以句点结尾。
- [x] Draft PR 正文包含 before/after routing matrix、兼容说明、测试结果和剩余限制。

---

## Progress

- [x] Phase 0 audit
- [x] Phase 1 routing baseline
- [x] Phase 2 taxonomy/catalog
- [x] Phase 3 public entry/runner refactor
- [x] Phase 4 compatibility aliases
- [x] Phase 5 internalization
- [x] Phase 6 validation and PR ([Draft PR #13](https://github.com/xLLM-AI/xllm-workflow/pull/13))
- [x] Architecture review blocking fixes
- [x] Fresh-task Codex routing dogfood (15/15 observed primary matches; direct history 1/1)

## Decision Log

### D-000: Establish the PR12 baseline

- Evidence: Issue #12; `main` and `origin/main` at `8e0a37e`; baseline `138 passed`; 19 registered workflow skill links; no broken links.
- Alternatives considered: continue the prior local branch; replay prior commits; restart from the merged PR11 baseline.
- Chosen option: restart from `origin/main` and treat Issue #12 as the only design and acceptance source.
- Compatibility impact: none; prior local work remains preserved on `feat/skill-taxonomy` and in a named stash.
- Rollback method: delete only the new topic branch and return to the preserved baseline or prior branch.

### D-001: Preserve all 19 current skill directories during audit

- Evidence: `docs/pr12/SKILL_INVENTORY.md`, `CURRENT_DAG.md`, and `ROUTING_CONFLICTS.md`; three independent subagent audits; baseline `138 passed`.
- Alternatives considered: reuse the pre-Issue taxonomy; immediately rename SOTA/batch skills; audit current main first.
- Chosen option: treat all rename, merge, split, visibility, and alias actions as hypotheses until Phase 1 routing evidence exists.
- Compatibility impact: none; Phase 0 changes documentation only.
- Rollback method: revert the Phase 0 documentation commit.

### D-002: Separate executable edges from documentation backlinks

- Evidence: `scripts/xllm_flow.py:1090-1139`, runner shell scripts, and `docs/pr12/CURRENT_DAG.md`.
- Alternatives considered: model every cross-reference as a call; model only subprocess edges; document both delegation and executable DAGs.
- Chosen option: use the acyclic runtime/delegation DAG and list apparent backlink cycles separately.
- Compatibility impact: none.
- Rollback method: revert the Phase 0 documentation commit.

### D-003: Use an auditable routing corpus instead of a fabricated model score

- Evidence: the baseline had 32 cases in `tests/routing/cases.yaml`; review renamed the JSON-parsed corpus to `tests/routing/cases.json` and expanded it to 34 cases covering every public skill. The original five missing lifecycle routes remain preserved as baseline evidence.
- Alternatives considered: claim a subjective routing percentage; invoke an unspecified model; use a deterministic expectation corpus with explicit current ambiguity.
- Chosen option: version a fixed prompt corpus and test its schema, coverage, references, allowed followups, forbidden primaries, and missing-route sentinel.
- Compatibility impact: none; Phase 1 does not modify skill routing behavior.
- Rollback method: revert the Phase 1 test/documentation commit.

### D-004: Use one machine-readable catalog as the taxonomy source

- Evidence: all 19 audited skills are represented in `skills/catalog.json`; `scripts/validate_skill_catalog.py` checks inventory coverage, identifiers, dependencies, visibility, priorities, and alias integrity; 14 focused tests pass.
- Alternatives considered: duplicate taxonomy fields in every `SKILL.md` frontmatter; infer taxonomy from prose; maintain one repository-level catalog.
- Chosen option: make `skills/catalog.json` the machine-readable taxonomy source and, after review, the installer canonical-directory source. Do not duplicate metadata in frontmatter. Codex runtime routing does not consume the catalog directly, so it is not described as a complete runtime routing SSOT.
- Compatibility impact: none; no skill is renamed, moved, deleted, or newly routed in this phase.
- Rollback method: revert the Phase 2 catalog, validator, and tests commit.

### D-005: Add a lifecycle facade and preserve independent runner names

- Evidence: Phase 1 cases `lifecycle-create`, `lifecycle-resume`, `lifecycle-finalize`, `lifecycle-archive`, and `internal-evidence` had no public canonical owner; explicit perf-only, accuracy-only, batch, build, service, and report cases each have a distinct outcome.
- Alternatives considered: make SOTA the lifecycle root; make eval the lifecycle root; add `xllm-experiment-lifecycle`; rename or merge all runners immediately.
- Chosen option: add `xllm-experiment-lifecycle` as a thin public facade over `scripts/xllm_flow.py`, narrow the four broad orchestrator descriptions, and preserve existing runner names and direct intents.
- Compatibility impact: additive public entry only. Existing skills remain at the same paths and retain their explicit routes. vLLM-Ascend/SGLang remain adapter- or artifact-level rather than full end-to-end claims.
- Rollback method: revert the Phase 3 commit; the underlying `xllm-flow` CLI and all prior skill paths remain unchanged.

### D-006: Preserve old names as canonical instead of inventing aliases

- Evidence: Phase 3 added one entry but renamed, moved, and deleted none; all 19 baseline IDs still map to their original directories; the routing corpus provides no failing case that a second name would improve.
- Alternatives considered: create aliases for unchanged names; rename runners for consistency; keep old names canonical and define a strict future alias contract.
- Chosen option: keep `aliases` empty for PR12, test preservation of every baseline canonical ID, require compatibility metadata for any future alias, and reject alias chains as well as loops, missing targets, and multiple targets.
- Compatibility impact: all existing invocations and links remain valid. There is no deprecation window because no old name is deprecated.
- Rollback method: revert the Phase 4 policy/test commit; no runtime implementation or skill path changes are involved.

### D-007: Internalize only delegated remote execution

- Evidence: inventory and routing cases show no ordinary primary intent for `ssh-remote-exec`; batch, eval, and server consume it as implementation support. Explicit build, service, perf, accuracy, and completed-artifact report cases each retain independent user outcomes. Fairness, evidence, checksum, and projection are already internal functions/scripts rather than skill entries.
- Alternatives considered: internalize every runner/gate/support skill; leave all skills implicitly routable; disable implicit invocation only for `ssh-remote-exec` while preserving explicit invocation.
- Chosen option: keep the directory and explicit `$ssh-remote-exec` capability, mark it internal in the catalog, and set `policy.allow_implicit_invocation: false`. Preserve all other direct routes.
- Compatibility impact: explicit remote execution remains available; ordinary prompts no longer receive it as an implicit candidate. No underlying SSH procedure changes.
- Rollback method: remove the policy file or restore implicit invocation and revert the Phase 5 commit.

### D-008: Validate routing and lifecycle without inventing an NPU workload

- Evidence: 20 canonical links refresh without skips or breakage; 19/19 baseline names resolve; 32/32 routing cases have one expected primary and zero missing lifecycle routes; synthetic create/finalize/archive and tamper-rejection tests pass; `npu-smi` shows a live process on device 4 but the Issue provides no pinned model, binary, workload, or experiment spec.
- Alternatives considered: start an arbitrary NPU serving task; treat unit tests alone as refresh proof; run filesystem refresh plus deterministic lifecycle smoke and record the hardware condition.
- Chosen option: execute the complete non-NPU validation surface and skip the conditional real NPU task because choosing an arbitrary workload would expand PR scope and yield non-comparable evidence.
- Compatibility impact: none; validation rebuilt the same 19 old canonical links plus the additive lifecycle link.
- Rollback method: restore the pre-refresh link inventory from `/tmp/pr12-skill-links-before.txt`; repository changes can be reverted phase by phase.

### D-009: Promote the orphan history entry to a formal public skill

- Evidence: the former `reference/pr_history/SKILL.md` defines a self-contained query goal, accepts model/keyword/framework/path inputs, returns matching dossiers and sections, and is implemented by the independently runnable `scripts/query.py`.
- Alternatives considered: promote it to `skills/model-pr-optimization-history/`; convert it to a plain README used only by SOTA; preserve the orphaned hybrid state.
- Chosen option: promote it to a public analyzer skill, keep dossiers under `reference/pr_history/`, add catalog/routing/install coverage, and have SOTA call it during Learn.
- Compatibility impact: additive discoverability; dossier paths and the top-level query script remain stable.
- Rollback method: remove the public skill, catalog item and direct routing case while preserving dossiers and `scripts/query.py`; if direct routing is intentionally retired, replace references with plain reference-document language rather than restoring orphan frontmatter.

### D-010: Keep routing claims at specification level until fresh-task dogfood

- Evidence: tests validate deterministic ownership sets, but Codex runtime routing uses injected skill metadata and does not execute `tests/routing/cases.json` or consume the catalog as a router.
- Alternatives considered: claim model-routing accuracy from unit tests; mark PR ready after refresh; require observed routing in a fresh task.
- Chosen option: keep PR #13 Draft and Definition of Done open until a new Codex task records real routing selections against representative prompts.
- Compatibility impact: none.
- Rollback method: not applicable; this is an acceptance constraint, not runtime behavior.

### D-011: Accept the refreshed routing taxonomy from isolated dogfood evidence

- Evidence: `docs/pr12/ROUTING_DOGFOOD.md` records 14 isolated fresh-task probes captured before
  reading `expected_primary`; 14/14 observed primaries match, lifecycle create/resume/finalize are
  3/3, ordinary prompts select `ssh-remote-exec` zero times, explicit `$ssh-remote-exec` remains
  selectable, and internal skills appear as implicit primary zero times. Catalog validation passes,
  the full suite reports 159 passed, and `git diff --check` passes.
- Alternatives considered: change SKILL descriptions without a mismatch; alter expected routes to
  fit observations; accept the observed 100% result without modifying routing metadata.
- Chosen option: preserve the current skill taxonomy and routing descriptions, add only the sealed
  dogfood evidence and validation status, keep PR #13 Draft, and hand it to human review without
  marking it Ready for Review.
- Compatibility impact: none; no skill, runtime, catalog, expected route, or invocation policy was
  changed.
- Rollback method: revert the dogfood documentation commit; the routing implementation and prior
  validation remain unchanged.

### D-012: Finalize lifecycle evidence paths and direct history routing evidence

- Evidence: the public lifecycle example now matches the real subprocess smoke at `perf/raw/` and
  `perf/metrics.json`; `--metrics-json`, `--artifact`, and `--kept-path` share the canonical metrics
  path. A new isolated history probe selected `model-pr-optimization-history`, bringing the bounded
  observed sample to 15/15 with direct history at 1/1.
- Alternatives considered: keep the stale `reports/metrics.json` example; weaken the lifecycle test
  to text matching; change routing expectations to fit the observation.
- Chosen option: align documentation with the existing performance evidence contract, retain the
  real CLI subprocess smoke, preserve all taxonomy and expected routes, and move PR #13 to Ready
  for Review after final validation.
- Compatibility impact: none; canonical skill names, locations, runtime behavior, and routing
  ownership are unchanged. vLLM-Ascend and SGLang remain experimental adapter/artifact scopes.
- Rollback method: revert the final polish commit; no runtime migration is required.
