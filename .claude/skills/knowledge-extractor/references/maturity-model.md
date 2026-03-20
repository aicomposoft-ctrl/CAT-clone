# Artifact Maturity Model

Lifecycle and versioning system for toolkit artifacts.

---

## Maturity Levels

| Level | Symbol | Name | Meaning | Trust Level |
|-------|--------|------|---------|-------------|
| 0 | 🔴 | **Alpha** | First extraction, untested outside source project | Low — use with caution |
| 1 | 🟡 | **Beta** | Used in 2+ projects, edge cases found and handled | Medium — works but watch for issues |
| 2 | 🟢 | **Stable** | Used in 3+ projects, well-documented, community-tested | High — can be trusted by AI agents |
| 3 | ⭐ | **Proven** | Core toolkit artifact, battle-tested, exemplary docs | Very high — reference implementation |

## Promotion Criteria

### 🔴 Alpha → 🟡 Beta

**ALL of these must be true:**
- [ ] Used successfully in at least 2 different projects
- [ ] At least 1 edge case discovered and handled
- [ ] "When to use" and "When NOT to use" sections refined
- [ ] At least 1 variant documented
- [ ] No project-specific references remain

### 🟡 Beta → 🟢 Stable

**ALL of these must be true:**
- [ ] Used successfully in at least 3 different projects
- [ ] All known edge cases documented
- [ ] Multiple variants documented (≥2)
- [ ] Performance characteristics known
- [ ] No open issues / known bugs
- [ ] Another developer (or AI agent) has used it without guidance

### 🟢 Stable → ⭐ Proven

**ALL of these must be true:**
- [ ] Used in 5+ projects
- [ ] Has been the subject of improvement iterations (v3+)
- [ ] Exemplary documentation (could serve as tutorial)
- [ ] Community or team consensus on quality
- [ ] Has related artifacts (complementary patterns/rules)

## Demotion Criteria

Artifacts can be demoted:

| From | To | When |
|------|----|------|
| Any | 🔴 Alpha | Breaking change in underlying tech makes it unreliable |
| Any | ❌ Deprecated | No longer applicable (library/framework retired) |
| ⭐ Proven | 🟢 Stable | Better alternative discovered |

## Versioning

### Version Format

```
v[MAJOR].[MINOR]
```

- **MAJOR** increment: Breaking change, fundamentally different approach
- **MINOR** increment: New variant, edge case fix, documentation improvement

### Changelog Block

Every artifact must have:

```markdown
## Maturity: 🟡 Beta
## Used in: project-a, project-b, project-c
## Extracted: 2026-01-15
## Last updated: 2026-03-01
## Version: v2.1
## Changelog:
- v2.1: Added Redis-backed variant, performance notes
- v2.0: Rewritten to use generic traits instead of concrete types
- v1.1: Fixed edge case with zero-length input
- v1.0: Initial extraction from project-a
```

### When to Increment Version

| Change Type | Version Bump |
|-------------|-------------|
| Fix edge case | Minor (v1.0 → v1.1) |
| Add new variant | Minor (v1.1 → v1.2) |
| Improve documentation | Minor |
| Change interface/API | Major (v1.x → v2.0) |
| Rewrite implementation | Major |
| Change target audience | Major |

## Provenance Tracking

### "Used in" Field

Track every project where the artifact was used:

```markdown
## Used in:
- project-a (v1.0, extracted here)
- project-b (v1.1, found edge case with empty arrays)
- project-c (v2.0, rewritten for async support)
```

### Source Attribution

Always record:
- **Original project** — where it was first discovered
- **Extraction date** — when it entered the toolkit
- **Extractor** — who performed the harvest (human or AI agent)

## Maturity in Context

### For AI Agents

When an AI agent encounters a toolkit artifact:

| Maturity | AI Behavior |
|----------|-------------|
| 🔴 Alpha | Use with explicit warning to user, suggest alternatives |
| 🟡 Beta | Use normally, mention known limitations |
| 🟢 Stable | Use confidently, reference documentation |
| ⭐ Proven | Use as reference implementation, recommend to others |

### For Human Developers

| Maturity | Developer Action |
|----------|-----------------|
| 🔴 Alpha | Review code carefully before using, provide feedback |
| 🟡 Beta | Use in non-critical paths, report edge cases |
| 🟢 Stable | Use freely, contribute improvements |
| ⭐ Proven | Recommend to team, use as template for new artifacts |

## Lifecycle Visualization

```
Discovery in project
    ↓
[🔴 Alpha v1.0] ← First extraction
    ↓ (used in 2nd project, edge case found)
[🟡 Beta v1.1]  ← Edge case fixed
    ↓ (rewritten for broader use)
[🟡 Beta v2.0]  ← Major rewrite
    ↓ (used in 3rd project, stable)
[🟢 Stable v2.1] ← Variant added
    ↓ (5+ projects, exemplary docs)
[⭐ Proven v3.0] ← Reference implementation
    ↓ (technology sunset)
[❌ Deprecated]  ← Archived
```
