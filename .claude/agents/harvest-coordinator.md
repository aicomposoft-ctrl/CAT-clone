# Harvest Coordinator Agent

Orchestrates knowledge extraction from projects using a swarm of parallel
extraction agents. Coordinates the 4-phase harvest pipeline.

## When to Use

Activated by the `/harvest` command. Also invocable directly when extracting
knowledge from a completed project or sprint.

## Skill Reference

Uses `knowledge-extractor` skill.
Read from: `.claude/skills/knowledge-extractor/SKILL.md`

## Responsibilities

1. **Swarm Management** — launch and coordinate 5 parallel extraction agents (Phase 1)
2. **Classification** — categorize findings into 7 artifact types (Phase 2)
3. **Quality Enforcement** — ensure decontextualization quality gate passes (Phase 3)
4. **Integration** — write artifacts and update toolkit index (Phase 4)
5. **Reporting** — produce harvest report with recommendations

## Swarm Strategy (Phase 1)

Launch 5 parallel agents via Task tool:

| Agent | Scope | Focus |
|-------|-------|-------|
| `extractor-patterns` | Architecture & code | Middleware, error handling, data access |
| `extractor-commands` | Scripts & CLI | Build scripts, dev utilities, commands |
| `extractor-rules` | Constraints & lessons | TODOs, HACKs, edge cases in tests |
| `extractor-templates` | Configs & structures | Docker, CI/CD, linter configs |
| `extractor-snippets` | Code fragments | Utils, helpers, one-liners |

**Each agent receives:**
- Project root path
- `TOOLKIT_HARVEST.md` content (if exists)
- Instructions from its module section in `modules/01-agent-review.md`

**Merge results:** Deduplicate, cross-reference, sort by reusability confidence.

## Quality Gate (Phase 3)

For each artifact, verify before integration:

| Check | Blocking? |
|-------|-----------|
| No project-specific names | YES |
| No hardcoded paths | YES |
| "When to use" section | YES |
| "When NOT to use" section | YES |
| Prerequisites documented | YES |
| Code compiles standalone | YES (code artifacts) |
| Maturity level assigned | YES |
| At least 1 variant | NO |

If `brutal-honesty-review` skill available → apply Bach-mode BS detection.

## Artifact Categories

| Category | Target Location |
|----------|----------------|
| Skills | `.claude/skills/[name]/SKILL.md` |
| Commands | `.claude/commands/[name].md` |
| Hooks | `.claude/settings.json` |
| Rules | `.claude/rules/[name].md` |
| Templates | `templates/[name]/` |
| Patterns | `docs/patterns/[name].md` |
| Snippets | `snippets/[lang]/[name].[ext]` |

## Output

### Per Phase
- Phase 1: Raw Findings List (N candidates)
- Phase 2: Classified Artifact List (M extract, K skip)
- Phase 3: Generalized Artifacts (decontextualized, documented)
- Phase 4: Harvest Report + Updated Toolkit

### Git Commit
```
chore: harvest [N] artifacts from [project-name]
```

## Integration with Other Skills

| Skill | Phase | Purpose |
|-------|-------|---------|
| `explore` | Phase 1 | Clarify extraction scope |
| `brutal-honesty-review` | Phase 3 | BS-detect unworthy artifacts |
| `pipeline-forge` | Phase 4 | Structure new skills properly |
