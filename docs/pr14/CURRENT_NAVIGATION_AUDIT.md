# PR14 Current Navigation Audit

Date: 2026-07-12

Baseline: `origin/main` at `6c66948ee62db132e30c5ec46fe582b3954919b5`, the tree-equivalent squash merge of PR #13.

## Method

Three isolated, read-only reviewers inspected the current repository before any public documentation changed:

- Reader A followed the first-time performance-optimization journey.
- Reader B followed the contributor and skill-maintainer journey.
- Reader C reviewed the skill architecture and generated-document feasibility.

## Reader A: First-Time User

The current path is reachable but requires roughly six transitions: root README, workspace initialization,
agent startup, prompt selection, `AGENTS.md` routing, then lifecycle and specialist skill instructions.
The main ambiguity is the relationship between `xllm-experiment-lifecycle` as control plane and
`xllm-npu-sota-loop` as the primary optimization workflow. The root page also lacks a documentation hub,
so `docs/pr12/` can look like current operating guidance instead of design history.

The audit also found older example inconsistencies in the SOTA prompt, standard workflow, and scripts guide.
Those are recorded as follow-up candidates; PR14 keeps its expected navigation scope and does not change skill
routing descriptions, invocation policy, or runtime behavior.

## Reader B: Maintainer

There is no single current guide connecting the required maintenance steps: decide skill versus script, edit
`SKILL.md`, update the catalog, add routing cases, refresh installed links, update curated navigation when public
concepts change, regenerate derived views, and run validation. These rules are distributed across README,
`AGENTS.md`, tests, the initializer, and PR12 history.

The maintainer path needs one canonical guide and a documentation hub. Generated and curated files must be
clearly separated. Historical PR12 inventory remains a compatibility record, not the new user entry point.

## Reader C: Architecture And Generation

The catalog already owns canonical discovery for 21 flat skill directories, so additive presentation metadata
can drive human views without changing installation or routing. Human role and exposure labels should be
explicit presentation fields rather than a renderer-side ID mapping. Generation must use fixed group/domain
ordering, canonical-ID sorting, stable relative links, no timestamps or local paths, and a read-only `--check`.

The renderer should generate only `skills/README.md` and `docs/architecture/skill-map.md`. Root landing pages and
the documentation hub remain curated. Tests must cover presentation validation, deterministic output, drift,
canonical link resolution, role exact-once coverage, public domain coverage, and internal visibility.

## Decisions For Milestones 1-5

1. Keep all canonical skill IDs and flat directories unchanged.
2. Add presentation-only `role_group` and `exposure` fields alongside the design's required metadata.
3. Keep catalog schema version 1 and add clear missing/incomplete presentation validation; the change is additive
   to routing and installer consumers but required for this repository version.
4. Describe dependencies as a graph unless cycle validation is present; do not overclaim a DAG.
5. Generate only the two catalog-derived skill views.
6. Add one curated documentation hub, concise bilingual front doors, a repository map, getting started guide,
   and one maintainer workflow.
7. Label PR12 documents as historical design records and preserve every existing path.
8. Treat the final three usability probes as bounded qualitative checks, not general usability accuracy.
