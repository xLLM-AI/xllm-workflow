# PR12 Skill Compatibility Policy

## Current Decision

PR12 Phase 3 did not rename, move, or delete any of the 19 baseline skill entries. Every old name
and directory remains canonical. The new `xllm-experiment-lifecycle` entry is additive, so this PR
needs no compatibility aliases.

Creating aliases without an actual rename would add competing public names and make routing less
deterministic. An empty `aliases` list is therefore the compatibility result for this PR, not an
unimplemented migration.

## Alias Contract

When a future change renames a skill, add exactly one catalog alias with:

- the old ID;
- one direct canonical target, never another alias;
- a description that says it is compatibility-only and must not win new primary routing;
- the release or PR that introduced it;
- objective removal conditions.

Aliases must not contain copied scripts or references. The canonical directory owns the only
implementation. Validation rejects missing targets, multiple targets, alias chains, and cycles.

## Migration Cycle And Removal

Keep a real alias for at least one documented migration cycle. Remove it only when all of these are
true:

1. repository docs, prompts, tests, and examples use the canonical name;
2. a skill-link refresh and old-name smoke show no active installation depends on the alias;
3. the deprecation window recorded in the alias has elapsed;
4. release notes identify the removal;
5. routing tests contain no expected or allowed route through the old name.

## Refresh Expectations

For PR12, refresh must produce links for all 20 canonical directories and no compatibility link.
For a future real rename, refresh must produce one canonical implementation link and a redirect or
equivalent compatibility link that resolves to it without copying implementation files.
