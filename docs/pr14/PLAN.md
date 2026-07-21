# PR #14 Design — Human-Facing Repository Information Architecture

> Repository: `xLLM-AI/xllm-workflow`  
> Proposed PR title: `docs: improve repository navigation and skill discovery.`  
> Execution owner: Codex  
> Review goal: make the repository understandable to a new human reader without changing skill behavior, canonical IDs, or runtime routing.

---

## 0. Execution gate: verify the PR #13 baseline first

Before implementing this design, Codex must verify the actual Git baseline.

Run:

```bash
git fetch origin
git status --short
git branch --show-current
git rev-parse HEAD
git rev-parse origin/main
gh pr view 13 --repo xLLM-AI/xllm-workflow \
  --json state,isDraft,mergedAt,mergeCommit,headRefOid,baseRefOid,url
git merge-base --is-ancestor c628f487630fcadc7e5a9247277d995b9a1c9ce4 origin/main
```

Expected condition:

- PR #13 is merged remotely; and
- `origin/main` contains PR #13 head `c628f487630fcadc7e5a9247277d995b9a1c9ce4`
  or its merge/squash-equivalent content; and
- `origin/main` contains `skills/catalog.json`, `xllm-experiment-lifecycle`,
  `model-pr-optimization-history`, and the PR #13 validation changes.

If remote `main` does not contain PR #13, **stop**. Do not implement PR #14 on an
unmerged local-only baseline. Record the discrepancy and ask the maintainer to
finish or identify the intended merge.

After verification, create a clean branch from current `origin/main`:

```bash
git switch --create docs/repository-information-architecture origin/main
```

---

## 1. Problem statement

PR #13 established a sound logical skill taxonomy and validated routing
ownership. The repository is now technically structured, but its human-facing
navigation still makes a new reader reconstruct the architecture from several
places:

- the root README mixes product positioning, installation, prompts, directory
  semantics, lifecycle details, architecture, and contribution rules;
- `AGENTS.md` contains a useful but flat task-to-skill table;
- `skills/` is physically flat, so browsing the directory does not reveal
  orchestration, execution, analysis, planning, gate, knowledge, development,
  and support roles;
- the catalog contains machine-readable taxonomy, but it does not yet render a
  polished human capability map;
- documentation entry points are distributed across `README*`, `AGENTS.md`,
  `scripts/README.md`, `docs/`, `reference/`, and `skills/*/SKILL.md`;
- historical design material under `docs/pr12/` is useful, but it should not
  appear to be the normal starting point for repository users;
- the English and Chinese landing pages can drift when public navigation
  changes.

The repository should answer these questions within a few minutes:

1. What problem does this repository solve?
2. What is fully supported, and what is experimental?
3. Where should I start for my task?
4. How do lifecycle, optimization, execution, analysis, and gates relate?
5. Which skill is the primary entry for a given intent?
6. Where do deterministic scripts, schemas, reference knowledge, and run
   evidence live?
7. How do I add or modify a skill without creating documentation drift?
8. Which documents are current user guides, architecture references,
   maintainer guides, or historical design records?

---

## 2. Goals

PR #14 should:

- make the root README a concise, task-oriented front door;
- add a clear documentation hub for different audiences;
- provide a catalog-generated human skill map grouped by role and domain;
- explain the repository architecture and evidence flow visually;
- distinguish user guides, architecture, maintainer guidance, references, and
  historical decisions;
- preserve stable canonical skill IDs and flat installable skill directories;
- keep human documentation derived from the same catalog used for skill
  discovery;
- prevent generated documentation and catalog metadata from drifting;
- keep English and Chinese root navigation conceptually aligned;
- preserve all PR #13 routing behavior and compatibility guarantees.

### Success criteria

A new reader should be able to:

- choose the correct top-level workflow from the root README;
- find all 21 canonical skills through a grouped capability index;
- understand the difference between orchestrator, runner, analyzer, planner,
  gate, knowledge/development support, and internal implementation;
- understand the difference between `skills/`, `scripts/`, `reference/`,
  `humanize/`, `runs/`, and `docs/`;
- locate the skill-authoring and catalog-maintenance instructions;
- see xLLM as the complete primary path and vLLM-Ascend/SGLang as limited
  adapter/artifact scopes;
- follow stable links without needing to inspect `docs/pr12/`.

---

## 3. Non-goals

This PR must not:

- rename, move, merge, split, deprecate, or delete canonical skills;
- create `skills/00-orchestration/`, `skills/10-execution/`, or other nested
  physical category directories;
- change any `name:` field in `SKILL.md`;
- change routing descriptions or invocation policies unless a documentation
  bug is proven and separately reviewed;
- change `xllm-flow`, benchmark, service, profiling, accuracy, build, or
  evidence semantics;
- add a new workflow gate or framework adapter;
- claim full vLLM-Ascend or SGLang end-to-end support;
- migrate historical run data;
- move `docs/pr12/` and break existing Issue/PR links;
- turn the catalog into a runtime model router;
- duplicate full skill metadata manually across multiple documents.

---

## 4. Core design decision: logical views, not physical skill directories

Keep the installable source layout stable:

```text
skills/
  catalog.json
  xllm-experiment-lifecycle/
  xllm-npu-sota-loop/
  xllm-npu-perf-runner/
  ...
```

Do **not** change it to:

```text
skills/
  00-orchestration/
  10-execution/
  20-analysis/
  ...
```

Reasons:

1. Codex routing uses skill metadata and invocation policy, not the source
   directory's parent category.
2. Flat canonical directories keep installation, explicit `$skill-name`
   invocation, old sessions, and repository links stable.
3. A skill has more than one useful classification axis. A single physical
   hierarchy cannot simultaneously express role, domain, lifecycle stage,
   framework scope, and visibility.
4. Catalog-generated views provide the desired human clarity without a large
   compatibility migration.

The human architecture should be presented through multiple generated views:

- **By role** — what kind of work the skill performs;
- **By domain** — which problem area it belongs to;
- **By user intent** — which skill is the preferred entry;
- **By dependency** — how orchestrators delegate to specialists;
- **By exposure** — public, delegated, explicit-only, or internal.

---

## 5. Target repository information architecture

```text
README.md                         # English front door
README_zh.md                      # Chinese front door
AGENTS.md                         # Agent constraints and exact routing contract

docs/
  README.md                       # Human documentation hub
  getting-started.md              # Installation + first synthetic lifecycle
  npu-ai-coding-standard-workflow.md
  architecture/
    repository-map.md             # Hand-authored repository/evidence architecture
    skill-map.md                  # Generated detailed role/domain/dependency view
  maintainers/
    adding-or-changing-a-skill.md # Catalog, SKILL, tests, docs, refresh workflow
  pr12/                           # Historical design record; linked but not a start page

skills/
  README.md                       # Generated human capability index
  catalog.json                    # Machine-readable taxonomy + presentation metadata
  <canonical-skill-id>/
    SKILL.md
    scripts/
    references/

scripts/
  README.md                       # Deterministic engine reference
  render_skill_docs.py            # Generates/checks human skill views
```

No existing stable document needs to move in this PR. The new `docs/README.md`
becomes the curated navigation layer.

---

## 6. Audience-specific navigation

### 6.1 Root README: the front door

The root README should be concise and answer “what is this, and where do I
start?” It should not be the full manual.

Recommended structure:

1. **Repository purpose**
   - one short paragraph;
   - xLLM primary support;
   - explicit experimental boundaries.

2. **Choose your path**
   - a compact task-to-entry table:

```text
Create/resume/finalize/archive a run  -> xllm-experiment-lifecycle
Optimize performance iteratively      -> xllm-npu-sota-loop
Run perf + accuracy suite              -> xllm-npu-eval-runner
Run one performance or accuracy test   -> corresponding runner
Review a fair performance claim        -> xllm-npu-benchmark
Collect/analyze profiling evidence     -> profiler / pipeline-analysis
Diagnose a failure                     -> accuracy-debug / incident-triage
Query historical model/PR lessons      -> model-pr-optimization-history
```

3. **Five-minute start**
   - initialize workspace;
   - start Codex;
   - copy a prompt or create an experiment spec;
   - link to `docs/getting-started.md`.

4. **How the pieces fit together**
   - one compact diagram;
   - lifecycle control plane delegates specialist work;
   - deterministic scripts produce evidence.

5. **Browse capabilities**
   - link to `skills/README.md`;
   - link to `docs/architecture/skill-map.md`.

6. **Documentation**
   - link to `docs/README.md`.

7. **Repository map**
   - short, seven-line map only;
   - detailed explanation moves to `docs/architecture/repository-map.md`.

8. **Contribution and support boundaries**
   - link, not a long embedded manual.

Target: keep each root README around 90–120 lines.

`README.md` and `README_zh.md` must preserve the same section order and the same
canonical links.

### 6.2 `docs/README.md`: documentation hub

Organize by reader goal, not by filesystem history.

Suggested content:

```text
Start here
- Getting started
- Standard workflow
- Skill capability map

Run workflows
- Experiment lifecycle
- Performance optimization
- Evaluation and benchmark
- Profiling and diagnosis
- Operator development

Understand the system
- Repository map
- Skill architecture
- Evidence and IO schemas
- Support boundaries

Maintain the repository
- Add or change a skill
- Deterministic scripts
- Catalog and generated docs
- Tests and validation

Design history
- PR #12 taxonomy/routing record
```

Historical documents may remain in place, but the hub should label them as
design records rather than current operating instructions.

### 6.3 `skills/README.md`: generated capability index

This is the primary human page when browsing `skills/`.

It should contain:

1. **How to choose a skill**
2. **Featured primary entries**
3. **By role**
4. **By domain**
5. **Public vs internal**
6. **Skill cards**
7. **Compatibility note**

Recommended human role groups:

#### Orchestration
- `xllm-experiment-lifecycle`
- `xllm-npu-sota-loop`
- `xllm-npu-eval-runner`
- `xllm-npu-batch-perf`

#### Execution
- `xllm-npu-perf-runner`
- `xllm-npu-accuracy-runner`
- `xllm-npu-server-manager`

#### Analysis and diagnosis
- `xllm-npu-benchmark`
- `xllm-npu-profiler`
- `xllm-npu-pipeline-analysis`
- `xllm-npu-accuracy-debug`
- `xllm-npu-incident-triage`

#### Planning and knowledge
- `xllm-npu-capacity-planner`
- `xllm-npu-compute-simulation`
- `model-pr-optimization-history`

#### Development and review
- `xllm-npu-code-review`
- `xllm-npu-triton-migration`
- `xllm-npu-xllm-ops-integration`

#### Gates and support
- `xllm-npu-build-gate`
- `xllm-npu-report-writer`
- `ssh-remote-exec` — explicit-only/internal

Do not create public skill entries for fairness validation, run-evidence
validation, checksums, projections, or Big-Rock implementation functions. They
remain deterministic internals owned by lifecycle or benchmark components.

### 6.4 `docs/architecture/repository-map.md`

Explain the repository using responsibility boundaries:

```text
User intent
  -> Skills: procedural decision and delegation
  -> Scripts: deterministic execution
  -> IO specs: contracts
  -> Runs: task evidence and ledgers
  -> Reference: durable static knowledge
  -> Humanize: promoted validated lessons
```

Clarify:

- `skills/` decides and delegates;
- `scripts/` executes deterministic operations;
- `reference/` stores stable knowledge and schemas;
- `runs/` stores per-task evidence and is not committed;
- `humanize/` stores promoted durable lessons;
- `docs/` explains the current system;
- `docs/pr12/` records the design history.

Include a Mermaid diagram and a concise directory table.

### 6.5 `docs/architecture/skill-map.md`

Generate this file from the catalog. It should include:

- role/domain matrix;
- public/internal counts;
- full dependency DAG;
- framework/backend scope table;
- canonical ID and display name;
- use-when and do-not-use-when summaries;
- outputs;
- links to each `SKILL.md`.

### 6.6 `docs/maintainers/adding-or-changing-a-skill.md`

Document one canonical maintenance workflow:

```text
1. Decide whether the capability is a skill or a deterministic script.
2. Choose role, domain, visibility, and primary intent.
3. Add/update SKILL.md.
4. Update skills/catalog.json.
5. Add routing specification cases.
6. Render generated docs.
7. Refresh installed skills.
8. Run validation and fresh-task routing probes when routing semantics change.
```

Include explicit rules:

- do not manually edit generated files;
- do not create aliases without a real rename;
- do not add a public skill for an internal validator;
- update README/README_zh/AGENTS together only when public concepts change;
- preserve xLLM vs experimental adapter claim boundaries.

---

## 7. Catalog presentation metadata

Extend each canonical skill entry with a small human-presentation object.

Recommended schema:

```json
{
  "id": "xllm-npu-sota-loop",
  "directory": "xllm-npu-sota-loop",
  "category": "orchestrator",
  "visibility": "public",
  "routing_priority": 10,
  "presentation": {
    "display_name": "Performance Optimization Loop",
    "display_name_zh": "性能优化闭环",
    "domain": "performance",
    "summary": "Run an evidence-driven, multi-round performance optimization campaign.",
    "summary_zh": "执行基于证据的多轮性能优化任务。",
    "outputs": [
      "bottleneck budget",
      "candidate ranking",
      "reviewable patches",
      "validated before/after evidence"
    ],
    "featured": true
  }
}
```

Required presentation fields:

- `display_name`
- `display_name_zh`
- `domain`
- `summary`
- `summary_zh`
- `outputs`
- `featured`

Allowed domain values should be explicit and validated, for example:

```text
lifecycle
performance
evaluation
accuracy
profiling
reliability
build
capacity
knowledge
development
reporting
remote-execution
```

Do not replace existing routing fields. Presentation metadata is for human
views; `primary_intents`, `negative_intents`, category, visibility,
dependencies, and scope remain the routing/taxonomy contract.

Upgrade the catalog schema version only if the repository's compatibility
policy requires it. A schema upgrade must have a clear validator error for old
or incomplete entries.

---

## 8. Generated documentation

Add:

```text
scripts/render_skill_docs.py
```

Supported commands:

```bash
python scripts/render_skill_docs.py
python scripts/render_skill_docs.py --check
```

Inputs:

- `skills/catalog.json`
- canonical `skills/*/SKILL.md` links/paths only where needed

Outputs:

- `skills/README.md`
- `docs/architecture/skill-map.md`

Generated files must start with:

```text
<!-- Generated by scripts/render_skill_docs.py. Do not edit manually. -->
```

### Renderer rules

- deterministic ordering;
- stable output across runs;
- all 21 canonical skills rendered exactly once in the role view;
- all public skills included in the domain view;
- internal skills shown in a clearly separate section;
- canonical links validated;
- no local paths;
- no unsupported framework claims;
- dependency graph uses canonical IDs;
- empty or missing presentation metadata fails generation;
- `--check` exits nonzero on drift without rewriting files.

Do not generate the root README or `docs/README.md`; those remain curated human
entry documents.

---

## 9. Visual and writing style

Use a consistent documentation style:

- task-oriented headings;
- short paragraphs;
- concise tables;
- one primary concept per section;
- canonical skill IDs in code formatting;
- human display names in prose;
- explicit “Use when” and “Do not use when” language;
- clear support labels:
  - **Supported**
  - **Experimental adapter**
  - **Artifact analysis only**
  - **Internal / explicit-only**
- avoid unexplained internal acronyms in landing pages;
- link to detailed references instead of duplicating them;
- preserve Chinese/English terminology consistently:
  - orchestrator / 编排器
  - runner / 执行器
  - analyzer / 分析器
  - planner / 规划器
  - gate / 门禁
  - knowledge / 知识
  - support / 支持工具

The repository should look intentional, not like a list of accumulated scripts.

---

## 10. Validation

Add or extend tests for:

### Catalog presentation metadata
- every canonical skill has all required presentation fields;
- domain is valid;
- outputs is a non-empty list of non-empty strings;
- featured is boolean;
- display names and summaries are non-empty;
- no duplicate canonical ID or directory.

### Generated documentation
- renderer output is deterministic;
- `--check` detects drift;
- every canonical skill appears exactly once in role view;
- every public skill appears in domain view;
- every generated link resolves;
- internal skill is clearly marked and not featured.

### Navigation
- root README and README_zh link to:
  - `docs/README.md`
  - `skills/README.md`
  - getting started
  - standard workflow;
- both root READMEs use the same major section order;
- docs hub links to all required current documents;
- historical PR #12 docs are labeled as design history;
- no generated file is manually divergent.

### Regression
Run:

```bash
python scripts/validate_skill_catalog.py
python scripts/render_skill_docs.py --check
pytest -q
git diff --check
```

Refresh skills and confirm:

```text
21/21 canonical installable
19/19 baseline names resolve
0 broken links
0 orphan SKILL.md
```

Because this PR does not change routing semantics, a new 15-case routing
dogfood is not required. Instead, use three isolated documentation usability
probes:

1. **New user probe** — identify how to start a performance optimization task.
2. **Operator probe** — locate service-only, benchmark, and incident workflows.
3. **Maintainer probe** — explain how to add a skill without editing generated
   docs manually.

Each probe should use only the public README/docs and report:

- answer;
- documents followed;
- dead ends or ambiguity;
- time/steps to find the answer.

Record results in:

```text
docs/architecture/DOCUMENTATION_DOGFOOD.md
```

Do not claim broad usability accuracy from three probes; treat them as bounded
qualitative checks.

---

## 11. Implementation milestones

### Milestone 0 — Human documentation audit

Use three subagents:

- **Reader A:** first-time user journey;
- **Reader B:** contributor/maintainer journey;
- **Reader C:** skill architecture and generated-doc feasibility.

Create:

```text
docs/pr14/CURRENT_NAVIGATION_AUDIT.md
docs/pr14/PLAN.md
```

Do not change public docs in this milestone.

### Milestone 1 — Catalog presentation metadata

- add presentation metadata for all 21 canonical skills;
- extend catalog validation;
- add focused tests;
- do not change skill names, descriptions, or invocation policy.

Suggested commit:

```text
refactor: add human-facing skill catalog metadata.
```

### Milestone 2 — Catalog-driven skill views

- add renderer;
- generate `skills/README.md`;
- generate `docs/architecture/skill-map.md`;
- add drift and link tests.

Suggested commit:

```text
docs: generate human-readable skill architecture views.
```

### Milestone 3 — Repository landing pages

- rewrite `README.md` and `README_zh.md` as concise front doors;
- add `docs/README.md`;
- add `docs/getting-started.md`;
- add `docs/architecture/repository-map.md`;
- link, do not duplicate, detailed workflow content.

Suggested commit:

```text
docs: clarify repository entry points and navigation.
```

### Milestone 4 — Maintainer documentation

- add skill-authoring/catalog/generated-doc guide;
- update `AGENTS.md` only with links or maintenance rules;
- preserve routing semantics and current detailed routing ownership.

Suggested commit:

```text
docs: document skill catalog maintenance workflow.
```

### Milestone 5 — Validation and usability dogfood

- run full validation;
- perform three isolated reader probes;
- fix navigation dead ends only;
- create `DOCUMENTATION_DOGFOOD.md`;
- create Draft PR.

Suggested commit:

```text
docs: record repository navigation validation.
```

---

## 12. Suggested PR scope

Expected files:

```text
README.md
README_zh.md
AGENTS.md
docs/README.md
docs/getting-started.md
docs/architecture/repository-map.md
docs/architecture/skill-map.md
docs/architecture/DOCUMENTATION_DOGFOOD.md
docs/maintainers/adding-or-changing-a-skill.md
docs/pr14/PLAN.md
docs/pr14/CURRENT_NAVIGATION_AUDIT.md
scripts/render_skill_docs.py
skills/README.md
skills/catalog.json
tests/test_skill_catalog.py
tests/test_skill_docs.py
tests/test_docs_navigation.py
```

Files outside this list require an explicit scope justification in the PR
description.

---

## 13. Definition of Done

- [ ] PR #13 is confirmed in the actual `main` baseline.
- [ ] Root README is a concise task-oriented front door.
- [ ] README and README_zh have aligned navigation and support claims.
- [ ] `docs/README.md` is the current human documentation hub.
- [ ] `skills/README.md` groups all canonical skills by role and domain.
- [ ] `docs/architecture/skill-map.md` is generated from the catalog.
- [ ] Repository architecture and evidence flow are documented visually.
- [ ] Maintainers have one documented skill-change workflow.
- [ ] Catalog presentation metadata covers all canonical skills.
- [ ] Generated docs are deterministic and checked for drift.
- [ ] Stable skill IDs, paths, routing descriptions, and invocation policies are unchanged.
- [ ] xLLM vs vLLM-Ascend/SGLang support boundaries remain accurate.
- [ ] Full repository tests and catalog validation pass.
- [ ] Skill refresh has no missing, broken, or orphan entries.
- [ ] Three isolated documentation usability probes complete without a blocking navigation dead end.
- [ ] Draft PR is created with the required title and validation summary.
- [ ] Codex does not merge the PR.

---

## 14. Codex execution instruction

Use this text to start the Codex task:

```text
Implement the design in the attached PR14 repository information architecture
document.

Repository:
xLLM-AI/xllm-workflow

First verify that PR #13 is actually contained in the latest origin/main.
The required baseline includes commit/content equivalent to
c628f487630fcadc7e5a9247277d995b9a1c9ce4.

If PR #13 is not in origin/main, stop and report the baseline discrepancy.
Do not build PR #14 on a local-only merge.

If the baseline is valid:

1. Read all applicable AGENTS.md files.
2. Save this design as docs/pr14/PLAN.md.
3. Create branch docs/repository-information-architecture from origin/main.
4. Use isolated subagents for:
   - new-user navigation audit;
   - maintainer navigation audit;
   - catalog/generator design review.
5. Execute Milestones 0 through 5 in order.
6. Preserve all canonical skill IDs, directories, routing descriptions, and
   invocation policies.
7. Do not create nested physical skill category directories.
8. Use skills/catalog.json as the source for generated skill views.
9. Keep root README/README_zh curated; generate only the skill index and detailed
   skill map.
10. Run catalog validation, generated-doc check, full pytest, diff check, skill
    refresh, link checks, and the three documentation usability probes.
11. Use small reviewable commits with messages ending in a period.
12. Create a Draft PR titled:
    docs: improve repository navigation and skill discovery.
13. Include before/after navigation, generated artifacts, test results, support
    boundaries, and remaining limitations in the PR body.
14. Do not merge the PR.
```
