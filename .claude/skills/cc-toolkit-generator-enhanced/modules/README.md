# CC-Toolkit-Generator-Enhanced — Modules

Modular phase architecture for the toolkit generator.
Each module is self-contained with: INPUT → PROCESS → OUTPUT → QUALITY GATE.

## Phase Modules (Core Pipeline)

| # | Module | File | Size | Purpose |
|---|--------|------|------|---------|
| 01 | Detect & Parse | `01-detect-parse.md` | 10K | Scan docs, detect pipeline type (SPARC/idea2prd), build IPM |
| 02 | Analyze & Map | `02-analyze-map.md` | 16K | Map documents to toolkit instruments with scoring engine |
| 03 | Generate P0 | `03-generate-p0.md` | 22K | Mandatory toolkit items (CLAUDE.md, rules, commands, skills) |
| 04 | Generate P1 | `04-generate-p1.md` | 24K | Recommended items + enterprise lifecycle + automation |
| 05 | Generate P2-P3 | `05-generate-p2p3.md` | 20K | Optional: TDD guide, DDD validators, MCP configs |
| 06 | Package & Deliver | `06-package-deliver.md` | 29K | Master validation checklist + delivery report |

## Extension Modules (Reusable Across Projects)

| # | Module | File | Size | Purpose |
|---|--------|------|------|---------|
| 07 | Harvest Feedback | `07-harvest-feedback.md` | 11K | Post-project learning loop (harvest → improve → generate) |
| 08 | Skill Composition | `08-skill-composition.md` | 12K | Dependency graph, copying, path rewriting, manifest |
| 09 | Cross-Project Learning | `09-cross-project-learning.md` | 18K | Pattern reuse via maturity model + relevance scoring |

## Execution Flow

```
01-detect-parse     → IPM (Internal Project Model)
02-analyze-map      → Instrument Map (scored items)
  ↓ [OPTIONAL]
09-cross-project    → Augmented Instrument Map (with proven patterns)
  ↓
03-generate-p0      → P0 files (mandatory)
  ↓ uses
08-skill-composition → Skills copied + paths rewritten
  ↓
04-generate-p1      → P1 files (recommended)
05-generate-p2p3    → P2-P3 files (optional)
  ↓
06-package-deliver   → Validated package + report
  ↓ [POST-PROJECT]
07-harvest-feedback  → Template improvements for next generation
```

## Module Interface Contract

Every module follows this structure:

```markdown
# Module: [Name]

## Input
[What this module receives — typed interface]

## Process
[Step-by-step execution with concrete logic]

## Output
[What this module produces — typed interface]

## Quality Gate
[Checklist: what must pass before proceeding]

## Dependencies
[Which skills/modules this calls via view()]

## Reusability
[How this module can be used outside cc-toolkit-generator-enhanced]
```

## Reusability Guide

These modules are designed for reuse in other IT contexts:

| Module | Reusable Pattern | Use Cases |
|--------|-----------------|-----------|
| 01 | Document type detection + project classification | Any pipeline needing input analysis |
| 02 | Scored document-to-artifact mapping | Any doc-driven generation system |
| 03-05 | Template-based tiered generation (P0/P1/P2) | Scaffolding, config generation |
| 06 | Multi-tier validation + budget enforcement | Any multi-file output system |
| 07 | Harvest → Improve → Generate feedback loop | CI/CD, doc generators, prompt libraries |
| 08 | Plugin/skill dependency resolution + path rewriting | Plugin installers, template repos |
| 09 | Registry + relevance scoring + maturity gating | Package recommendation, best practices |
