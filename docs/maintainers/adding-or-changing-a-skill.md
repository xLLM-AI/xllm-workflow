# Adding Or Changing A Skill

Use this workflow to preserve canonical discovery, routing ownership, generated documentation, and installed links.

## 1. Decide skill or script

Create a skill when the capability requires reusable procedural judgment, sequencing, or delegation. Put deterministic execution and validation in `scripts/` or a skill-local script. Do not create a public skill for an internal evidence validator, checksum, projection, fairness function, or Big-Rock implementation detail.

## 2. Define the contract

Choose a stable canonical ID and flat directory `skills/<canonical-id>/`. Define `name` and routing `description` in `SKILL.md`, then decide:

- category and human role;
- domain and visibility;
- primary and negative intents;
- dependencies;
- lifecycle, framework, and backend scopes;
- user-facing outputs.

Do not create physical category directories such as `skills/00-orchestration/`. Do not create an alias unless a real rename requires compatibility; aliases must point directly to one canonical target.

## 3. Add or update `SKILL.md`

Keep the procedure concise and move detailed material to `references/`. Preserve canonical IDs and existing descriptions unless the change intentionally and separately reviews routing behavior. Internal skills that are explicit-only must retain `agents/openai.yaml` with implicit invocation disabled.

## 4. Update the catalog

Edit `skills/catalog.json`. Routing fields own machine-readable taxonomy and discovery. The `presentation` object owns human display name, role, domain, exposure, summaries, outputs, and featured status. Presentation metadata must not change routing behavior.

Validate immediately:

```bash
python scripts/validate_skill_catalog.py
```

## 5. Update routing cases

For a new public outcome or a routing-semantics change, update `tests/routing/cases.json` and `tests/test_skill_routing.py`. Do not change `expected_primary` merely to hide an observed mismatch. Internal skills cannot be expected primaries.

## 6. Render generated documentation

Never manually edit these generated files:

- `skills/README.md`
- `docs/architecture/skill-map.md`

Regenerate and check them:

```bash
python scripts/render_skill_docs.py
python scripts/render_skill_docs.py --check
```

Root `README.md`, `README_zh.md`, `docs/README.md`, and architecture prose are curated. Update both root READMEs and `AGENTS.md` together only when public concepts or navigation change.

## 7. Refresh installed skills

Use the mode that matches the agent launch location:

```bash
python scripts/init_xllm_workspace.py
python scripts/init_xllm_workspace.py --mode xllm --agent codex
```

Confirm all canonical entries install, no real directory was skipped unexpectedly, and no symlink is broken. Start a new agent task after refresh when validating injected metadata.

## 8. Validate and probe

```bash
python scripts/validate_skill_catalog.py
python scripts/render_skill_docs.py --check
pytest -q
git diff --check
```

Confirm the installer set matches the catalog, all baseline names still resolve, and no orphan `SKILL.md` exists. Run fresh-task routing probes only when routing semantics changed; documentation-only navigation changes use bounded reader probes instead.

## Support and compatibility rules

- xLLM on Ascend is the complete primary workflow.
- vLLM-Ascend and SGLang remain limited to declared experimental adapter or artifact-analysis scopes.
- Do not claim full framework support from a build adapter or an analyzable artifact.
- Preserve existing canonical IDs, paths, and explicit invocation behavior unless a separately approved migration requires change.
