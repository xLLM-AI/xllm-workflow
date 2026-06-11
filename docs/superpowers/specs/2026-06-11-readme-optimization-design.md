# README Optimization Design

Date: 2026-06-11

## Goal

Compress both README.md and README_zh.md from ~260 lines to ~60-70 lines, following the "Audience-Specific Docs" principle: human docs are macro and minimal; Agent-level details (skill routing, phase descriptions, evidence contracts) belong in AGENT.md.

## Problem

Current READMEs violate multiple architectural principles:
- **SSOT violation**: Skill routing table duplicates AGENT.md; evidence contracts duplicate reference/io_specs/
- **Audience isolation violation**: Phase 0-6 details are Agent-level instructions, not human-level overview
- **Keep It Simple violation**: 267 lines for a human landing page is excessive; "What Is Included" and "Repository Layout" overlap

## Design

### Keep (human needs)
1. One-line positioning + who it's for + what it's NOT (merged into intro paragraph)
2. Quick Start: install skills → pick prompt → run evidence loop (3 steps, unchanged)
3. Directory overview: one concise tree (merges "What Is Included" + Repository Layout)
4. Architecture diagram (existing PNG, unchanged)
5. Core workflow: one sentence + link to docs/ and AGENT.md
6. Contribution guidelines: 3-5 rules
7. Language switcher + License note

### Delete (Agent-level or duplicated)
- Skills table (11 rows) — exists in AGENT.md
- Example Tasks (4 examples) — prompts/ directory self-contains usage
- Evidence Contracts table — exists in reference/io_specs/
- Core Workflow Phase 0-6 details — exists in AGENT.md and docs/
- Architecture 4-layer table — diagram is sufficient
- "What Is Included" table — merged into directory tree
- Requirements section — merged into intro paragraph
- "Who This Is For" standalone section — merged into intro

### Target structure (English)
```
# xLLM AI Coding Workflow
[Language switcher]
[1-paragraph intro: what, who, what-it's-not, hardware requirement]
## Quick Start
  1. Install Skills (symlink script, unchanged)
  2. Pick a Prompt (4-row table, unchanged)
  3. Evidence Loop (one line + link)
## Directory Overview (compact tree)
## Architecture (diagram + one sentence)
## Contribution Guidelines (5 rules)
## License
```

### Target structure (Chinese)
Same structure, Chinese content.