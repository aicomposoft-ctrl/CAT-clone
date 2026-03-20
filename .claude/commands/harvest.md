---
description: >
  Knowledge extraction from the current project into reusable toolkit artifacts.
  Scans codebase, classifies findings, decontextualizes, and integrates into toolkit.
  $ARGUMENTS: mode (quick/full/marker) + optional scope ("only patterns", "only rules", etc.)
---

# /harvest $ARGUMENTS

## Role

Knowledge harvester. You extract reusable artifacts from the current project —
patterns, commands, hooks, rules, templates, snippets, skills — and integrate
them into the toolkit as generalized, documented, versioned entries.

## Skill Reference

Read the skill: `.claude/skills/knowledge-extractor/SKILL.md`

**IMPORTANT:** Read the skill BEFORE executing. It contains:
- 4-phase pipeline with checkpoints
- Swarm agent definitions for Phase 1
- 7 artifact categories with criteria
- Decontextualization guide
- Quality gate for Phase 3
- Templates for all outputs

## Quick Reference

### Modes

| Mode | Trigger | What Happens |
|------|---------|-------------|
| `marker` | `/harvest marker [description]` | Append to TOOLKIT_HARVEST.md |
| `quick` | `/harvest quick` or `/harvest` | Auto scan + classify + report (no checkpoints) |
| `full` | `/harvest full` | 4-phase pipeline with checkpoints |

### Execution

1. Determine mode from $ARGUMENTS (default: quick)
2. Read skill: `.claude/skills/knowledge-extractor/SKILL.md`
3. If mode == marker: create/append TOOLKIT_HARVEST.md, done
4. If mode == quick: run all 4 phases without checkpoints
5. If mode == full: run with checkpoints after each phase

### Phase Summary

```
Phase 1: AGENT REVIEW — scan codebase with 5 parallel agents
Phase 2: CLASSIFY — categorize into 7 artifact types, filter exclusions
Phase 3: DECONTEXTUALIZE — generalize, document, version
Phase 4: INTEGRATE — write to toolkit, update index, harvest report
```

### Module References

| Phase | Module |
|-------|--------|
| Phase 1 | `.claude/skills/knowledge-extractor/modules/01-agent-review.md` |
| Phase 2 | `.claude/skills/knowledge-extractor/modules/02-classify.md` |
| Phase 3 | `.claude/skills/knowledge-extractor/modules/03-decontextualize.md` |
| Phase 4 | `.claude/skills/knowledge-extractor/modules/04-integrate.md` |

### Reference Files

| Topic | File |
|-------|------|
| Artifact categories | `.claude/skills/knowledge-extractor/references/artifact-categories.md` |
| Maturity model | `.claude/skills/knowledge-extractor/references/maturity-model.md` |
| Decontextualization | `.claude/skills/knowledge-extractor/references/decontextualization-guide.md` |

### Templates

| Template | File |
|----------|------|
| TOOLKIT_HARVEST.md | `.claude/skills/knowledge-extractor/templates/toolkit-harvest.md` |
| Artifact card | `.claude/skills/knowledge-extractor/templates/artifact-card.md` |
| Harvest report | `.claude/skills/knowledge-extractor/templates/harvest-report.md` |

## Checkpoint Commands (full mode)

| Command | Action |
|---------|--------|
| `ок` | Next phase |
| `добавь [finding]` | Add manual finding |
| `убери #N` | Remove finding |
| `переклассифицируй #N` | Change category |
| `доработай #N` | Improve artifact |
| `покажи #N` | Preview artifact |

## Critical Rules

### ALWAYS
- Read skill SKILL.md before executing
- Use swarm agents (Task tool) for Phase 1 — parallel extraction
- Apply exclusion filter in Phase 2 (no domain code, no unvalidated patterns)
- Decontextualize in Phase 3 (no project-specific references)
- Assign maturity level to every artifact
- Record provenance (source project, date)

### NEVER
- Don't copy code verbatim — always decontextualize
- Don't extract domain-specific business logic
- Don't extract library workarounds without expiry dates
- Don't skip Phase 3 — undecontextualized artifacts are tech debt
- Don't set maturity higher than 🔴 Alpha for first extraction
