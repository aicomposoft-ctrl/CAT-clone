# Phase 4: Integrate

Write generalized artifacts to the toolkit and update the index.

## Goal

Place each artifact in its correct toolkit location, handle version conflicts,
and produce a comprehensive Harvest Report.

## Integration Process

### Step 1: Determine Target Location

Each artifact category has a default target:

| Category | Default Target | Alternative |
|----------|---------------|-------------|
| Skills | `.claude/skills/[name]/SKILL.md` | External toolkit repo |
| Commands | `.claude/commands/[name].md` | External toolkit repo |
| Hooks | `.claude/settings.json` or `.claude/hooks/` | git hooks |
| Rules | `.claude/rules/[name].md` | CLAUDE.md inline |
| Templates | `templates/[name]/` or `.claude/templates/` | Standalone repo |
| Patterns | `docs/patterns/[name].md` or `patterns/` | Knowledge base |
| Snippets | `snippets/[lang]/[name].[ext]` or inline in docs | Gist/snippet manager |

**Target selection:**
- If integrating into current project → `.claude/` or project root
- If integrating into external toolkit → specify toolkit path
- If creating new repo → use pipeline-forge to scaffold

### Step 2: Handle Existing Artifacts

When an artifact with the same name already exists:

| Scenario | Action |
|----------|--------|
| New artifact | Write directly |
| Same name, different version | Merge: update version, add new variants |
| Same name, same content | Skip (already extracted) |
| Conflict (different approach) | Show both, ask user which to keep |

**Version merge process:**
1. Read existing artifact
2. Compare with new extraction
3. If new adds value → increment version, add to changelog
4. If new is different approach → present as variant
5. Update maturity level if warranted

### Step 3: Write Artifacts

For each artifact:

1. Create file at target location
2. Ensure directory exists
3. Write using `templates/artifact-card.md` format
4. Verify file was written successfully

**Skills (special handling):**
If artifact is a Skill, use pipeline-forge's skill anatomy:
```
.claude/skills/[skill-name]/
├── SKILL.md
├── references/    (if needed)
└── templates/     (if needed)
```

### Step 4: Update Toolkit Index

After all artifacts are written, update the toolkit index.

**If CLAUDE.md is the index:**
Add/update the toolkit section:

```markdown
## Toolkit Artifacts

### Skills
| Skill | Maturity | Description | Source |
|-------|----------|-------------|--------|
| [name] | 🔴/🟡/🟢 | [desc] | [project], [date] |

### Patterns
| Pattern | Maturity | Description | Source |
|---------|----------|-------------|--------|
| [name] | 🔴/🟡/🟢 | [desc] | [project], [date] |

[... for each category with artifacts]

Last harvest: [DATE]
Total artifacts: [N]
```

**If standalone manifest:**
Write to `.claude/toolkit-manifest.json`:
```json
{
  "last_harvest": "2026-03-01",
  "artifacts": [
    {
      "name": "retry-with-backoff",
      "category": "pattern",
      "maturity": "alpha",
      "path": "docs/patterns/retry-with-backoff.md",
      "source_project": "api-gateway",
      "extracted": "2026-03-01",
      "version": 1
    }
  ]
}
```

### Step 5: Generate Harvest Report

Produce a summary report using `templates/harvest-report.md`:

```markdown
# Harvest Report: [Project Name]
Date: [DATE]

## Summary
| Metric | Value |
|--------|-------|
| Files scanned | [N] |
| Candidates found | [M] |
| Artifacts extracted | [K] |
| Artifacts skipped | [J] |
| New artifacts | [X] |
| Updated artifacts | [Y] |

## Extracted Artifacts

| # | Name | Category | Maturity | Location |
|---|------|----------|----------|----------|
| 1 | [name] | [cat] | 🔴 | [path] |

## Skipped Items (with reasons)

| # | Name | Reason |
|---|------|--------|
| 1 | [name] | [reason] |

## Toolkit Status

Total artifacts in toolkit: [N]
- 🔴 Alpha: [X]
- 🟡 Beta: [Y]
- 🟢 Stable: [Z]

## Recommendations

- [Artifact X] → Consider promoting to 🟡 Beta after use in next project
- [Pattern Y] → Needs variant for [framework Z]
- Run next harvest after: [project/sprint/milestone]
```

### Step 6: Clean Up

1. Mark extracted items as done in `TOOLKIT_HARVEST.md` (check the checkboxes)
2. Optionally archive `TOOLKIT_HARVEST.md` to `docs/harvest-history/`
3. Git commit: `chore: harvest [N] artifacts from [project-name]`

## Git Commit Convention

```
chore: harvest [N] artifacts from [project-name]

Extracted:
- [category]: [artifact-name] (v[N])
- [category]: [artifact-name] (new)
```

## Output

- Written artifact files at their target locations
- Updated toolkit index
- Harvest Report at `docs/harvest-report-[date].md`
- Checked off `TOOLKIT_HARVEST.md` items
- Git commit with harvest summary
