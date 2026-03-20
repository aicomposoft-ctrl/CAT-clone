# Maturity Integration for Generated Toolkit Items

Tags, tracks, and promotes generated toolkit items using the knowledge-extractor's
4-level maturity model (Alpha / Beta / Stable / Proven).

---

## Maturity Levels

| Level | Symbol | Name | Trust | Auto-inject threshold (Module 09) |
|-------|--------|------|-------|-----------------------------------|
| 0 | Alpha | First generation, untested beyond source project | Low | Never auto-include |
| 1 | Beta | Validated in 2+ projects, edge cases handled | Medium | Relevance >= 70, user confirms |
| 2 | Stable | 3+ projects, well-documented, independently usable | High | Relevance >= 60 |
| 3 | Proven | 5+ projects, battle-tested, reference quality | Very High | Relevance >= 50 |

## Default Maturity Assignment

Every item produced by the generator starts at **Alpha** unless it was injected
from the cross-project registry at a higher level.

### Tagging Rules by Generation Phase

| Generator Phase | Item Types | Default Maturity | Override Condition |
|-----------------|-----------|------------------|-------------------|
| P0 (Mandatory) | CLAUDE.md, rules, /start, /feature, /myinsights, settings.json, lifecycle skills | Alpha | Proven registry artifact replaces default |
| P1 (Recommended) | Agents, /next, /plan, /go, /run, /docs, feature-navigator | Alpha | Stable+ registry artifact replaces default |
| P2-P3 (Optional) | TDD guide, DDD validators, MCP configs | Alpha | Beta+ registry artifact recommended |
| Injected (Module 09) | Any category from registry | Inherited from registry | N/A -- keeps its maturity |

Lifecycle skills copied via Module 08 (sparc-prd-mini, explore, goap-research,
problem-solver-enhanced, requirements-validator, brutal-honesty-review) are
**shared upstream skills** -- excluded from the manifest and tracked in the
shared skill registry instead.

## Maturity Manifest

Each project gets `.claude/maturity-manifest.json` (built by Module 06). This is
the single source of truth for toolkit item maturity within the project.

### Template

```json
{
  "schema_version": "1.0",
  "project": "{{PROJECT_NAME}}",
  "generated_at": "{{ISO_DATE}}",
  "generator_version": "cc-toolkit-generator-enhanced",
  "items": [
    {
      "id": "rule:git-workflow",
      "path": ".claude/rules/git-workflow.md",
      "category": "rule",
      "phase": "P0",
      "maturity": "Alpha",
      "version": "v1.0",
      "source": "generated",
      "source_project": null,
      "usage_count": 1,
      "promoted_at": null,
      "notes": null
    },
    {
      "id": "command:feature",
      "path": ".claude/commands/feature.md",
      "category": "command",
      "phase": "P0",
      "maturity": "Alpha",
      "version": "v1.0",
      "source": "generated",
      "source_project": null,
      "usage_count": 1,
      "promoted_at": null,
      "notes": null
    },
    {
      "id": "rule:security",
      "path": ".claude/rules/security.md",
      "category": "rule",
      "phase": "P0",
      "maturity": "Stable",
      "version": "v2.1",
      "source": "registry",
      "source_project": "project-alpha",
      "usage_count": 4,
      "promoted_at": "2026-02-10",
      "notes": "Injected by Module 09, relevance 82"
    }
  ],
  "summary": {
    "total": 0,
    "alpha": 0,
    "beta": 0,
    "stable": 0,
    "proven": 0
  }
}
```

### Field Reference

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | `{category}:{short-name}` -- unique within project |
| `path` | string | Relative path from project root |
| `category` | enum | `rule`, `command`, `agent`, `skill`, `hook`, `template`, `pattern`, `snippet` |
| `phase` | enum | `P0`, `P1`, `P2`, `P3` -- generation phase |
| `maturity` | enum | `Alpha`, `Beta`, `Stable`, `Proven` |
| `version` | string | Semantic version `v{MAJOR}.{MINOR}` |
| `source` | enum | `generated` (new) or `registry` (injected from cross-project registry) |
| `source_project` | string? | Original project name if sourced from registry |
| `usage_count` | number | How many projects have used this item |
| `promoted_at` | string? | ISO date of last maturity promotion |
| `notes` | string? | Free-text context (relevance score, edge cases, etc.) |

## Promotion Flow

Maturity promotes as the item is reused across projects. Promotion is tracked
both in the per-project manifest and in the cross-project registry.

### Promotion Criteria

```
Alpha -> Beta    (all required):
  - Used in 2+ distinct projects
  - At least 1 edge case discovered and handled
  - "When NOT to use" guidance documented
  - No project-specific references remain

Beta -> Stable   (all required):
  - Used in 3+ distinct projects
  - All known edge cases documented
  - Multiple variants documented (>= 2)
  - Successfully used by another developer or AI agent without guidance

Stable -> Proven (all required):
  - Used in 5+ distinct projects
  - Version >= v3.0 (iterated on meaningfully)
  - Exemplary documentation (could serve as tutorial)
  - Has complementary artifacts (related patterns/rules)
```

### Promotion Triggers

Checks run at two points: (1) **Module 09** -- after injecting a registry
artifact, increment `usage_count` and evaluate; (2) **/harvest** -- when
extracting from a completed project, compare against registry and evaluate.
Promotions are **recommendations** in the learning report; a reviewer confirms.

### Demotion

| From | To | Trigger |
|------|----|---------|
| Any | Alpha | Breaking change in underlying technology |
| Any | Deprecated | Technology/framework retired |
| Proven | Stable | Superior alternative discovered |

## Cross-Project Learning Integration (Module 09)

Module 09 uses maturity to decide what to inject into a new toolkit:

```
1. SCAN registry for artifacts matching project IPM
2. COMPUTE relevance score per artifact (0-100)
3. FILTER by maturity + relevance:
   - Proven  + relevance >= 50 -> inject into P0
   - Stable  + relevance >= 60 -> inject into P1
   - Beta    + relevance >= 70 -> recommend in P2 (user confirms)
   - Alpha   -> report only, never inject
4. INJECT passing artifacts into generation, replacing defaults
5. RECORD each injection in maturity-manifest.json with source=registry
6. APPEND usage record to registry usage-log.jsonl
7. EVALUATE promotion candidates, write to learning report
```

### Source Field Convention

- `source: "registry"` -- item injected from cross-project registry. Inherits
  maturity, version, usage_count, and source_project from the registry entry.
  The `notes` field records relevance score and match details.
- `source: "generated"` -- item created fresh by the generator. Starts at
  Alpha v1.0 with usage_count 1 and null source_project.

See the JSON template above for concrete examples of both cases.

## Generator Responsibilities

| Module | Maturity Responsibility |
|--------|------------------------|
| 01 (Detect & Parse) | None |
| 02 (Analyze & Map) | None |
| 03 (Generate P0) | Tag each output item as Alpha v1.0 unless replaced by injection |
| 04 (Generate P1) | Tag each output item as Alpha v1.0 unless replaced by injection |
| 05 (Generate P2-P3) | Tag each output item as Alpha v1.0 unless replaced by injection |
| 06 (Package & Deliver) | Build `maturity-manifest.json`, compute summary counts |
| 07 (Harvest Feedback) | Update registry maturity based on project outcomes |
| 08 (Skill Composition) | Exclude copied lifecycle skills from manifest |
| 09 (Cross-Project Learning) | Inject registry items, inherit maturity, record usage, recommend promotions |
