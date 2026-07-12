# Documentation Usability Dogfood

Date: 2026-07-12

These are three isolated, bounded qualitative probes of the public README and documentation paths. They are not a general usability score and do not validate runtime routing.

## Method

Each reader received one role and could use only public README/docs plus directly linked public skill documents. Readers did not inspect the PR14 design, tests, or catalog source, did not run workflow commands, and did not modify files.

## Probe 1: New performance-optimization user

### Answer

Start from the root task table with `xllm-npu-sota-loop`. Initialize the workspace, start the agent, pin a real experiment spec, and let SOTA own optimization decisions while `xllm-experiment-lifecycle` owns run state and evidence. Establish a warmed baseline, profile and pass the Big-Rock gate, iterate one hypothesis at a time, then validate and finalize.

### Documents followed

1. `README.md`
2. `docs/getting-started.md`
3. `skills/README.md`
4. `skills/xllm-npu-sota-loop/SKILL.md`
5. `skills/xllm-experiment-lifecycle/SKILL.md`
6. `docs/npu-ai-coding-standard-workflow.md`

The primary entry was found on the first page. A full operational mental model took four to six pages.

### Dead ends or ambiguity

No blocking navigation dead end. The remaining learning cost is operational depth: prerequisites, a fully populated real spec, expected successful artifacts, and the complete initialization-to-baseline sequence remain distributed across detailed documents. Core execution skills are Chinese while the English landing guides are English. These are recorded limitations rather than routing or taxonomy defects.

## Probe 2: Operator workflows

### Answer

- Service-only lifecycle: `xllm-npu-server-manager`.
- Fair benchmark or publishable claim: `xllm-npu-benchmark`.
- Runtime or build incident: `xllm-npu-incident-triage`.

### Documents followed

Benchmark and incident were one jump from the root task table. Service-only originally required a detour through `skills/README.md`; the root table and docs hub now link it directly.

### Dead ends or ambiguity

No blocking dead end after the navigation fix. Detailed skills still require readers to understand delegation: benchmark may request missing measurements, incident replay may need build-gate artifacts, and remote service work can explicitly delegate SSH. Those boundaries are intentionally procedural rather than duplicated in the landing page.

## Probe 3: Skill maintainer

### Answer

Use the eight-step maintainer workflow: decide skill versus script; define the contract; add or update `SKILL.md`; update catalog taxonomy and presentation; update routing cases when semantics change; regenerate the two derived views; refresh the appropriate install mode; validate and run the appropriate bounded probes.

Never manually edit `skills/README.md` or `docs/architecture/skill-map.md`.

### Documents followed

1. `README.md`
2. `docs/README.md`
3. `docs/maintainers/adding-or-changing-a-skill.md`
4. Generated skill and architecture views for confirmation

The complete workflow is available from one maintainer guide. The docs hub now links the guide rather than renderer source, and the guide has an explicit refresh-mode decision table.

### Dead ends or ambiguity

No blocking dead end. Remaining limitations include the lack of a separate approved rename/alias migration guide, an explicit template for a brand-new internal policy file, and copy-ready commands for every count assertion. Full validation still catches those contracts.

## Outcome

- Blocking navigation dead ends: **0** after two small navigation fixes.
- New-user primary selection: **1 page**.
- Operator primary selection: **1-2 pages**.
- Maintainer canonical workflow: **3 pages from root, one consolidated guide**.
- Canonical IDs, directories, routing descriptions, and invocation policies changed: **0**.

The probes support the bounded conclusion that the new entry points are navigable for the three tested roles. They do not claim broad documentation usability accuracy.
