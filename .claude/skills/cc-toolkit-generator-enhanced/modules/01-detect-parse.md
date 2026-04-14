# Module: Detect & Parse

Phase 1 of the CC-Toolkit-Generator Enhanced pipeline.
Scans the documentation directory, detects the pipeline type, identifies project
characteristics, and builds the Internal Project Model (IPM) used by all
subsequent modules.

---

## Input

| Parameter | Type | Description |
|-----------|------|-------------|
| `docs_path` | string | Path to documentation directory. In Claude.ai context this is `/mnt/user-data/uploads/`. In Claude Code / replicate context this is `docs/` (project root). |

No prior module output is required. This is the foundation module.

---

## Process

### Step 1: Scan for Documents

Scan `docs_path` recursively and catalog every file by category.

```
SCAN docs_path FOR:
  # SPARC pipeline files (top-level or docs/)
  PRD.md
  Solution_Strategy.md
  Specification.md
  Pseudocode.md
  Architecture.md
  Refinement.md
  Completion.md
  Research_Findings.md
  Final_Summary.md
  CLAUDE.md              # base CLAUDE.md from docs, if present

  # idea2prd-manual pipeline files
  docs/prd/PRD.md
  docs/ddd/strategic/    # bounded-contexts.md, context-map.md
  docs/ddd/tactical/     # aggregates/, entities/, value-objects/, events/, repositories/
  docs/adr/*.md          # ADR-001-*.md, ADR-002-*.md, ...
  docs/c4/*.mermaid      # context.mermaid, container.mermaid, component.mermaid
  docs/pseudocode/*.pseudo
  docs/tests/*.feature   # Gherkin scenarios
  docs/fitness/*.md      # fitness-functions.md
  docs/completion/COMPLETION_CHECKLIST.md
  docs/INDEX.md

  # .ai-context integration files
  .ai-context/README.md
  .ai-context/architecture-summary.md
  .ai-context/key-decisions.md
  .ai-context/domain-glossary.md
  .ai-context/bounded-contexts.md
  .ai-context/coding-standards.md
  .ai-context/fitness-rules.md
  .ai-context/pseudocode-index.md
```

If **no documents found at all**: halt and ask the user to upload SPARC or
idea2prd documentation.

### Step 2: Detect Pipeline Type

Apply the following detection logic in priority order:

```python
def detect_pipeline(docs_path: str) -> str:
    has_ddd       = exists(f"{docs_path}/docs/ddd/")
    has_ai_context = exists(f"{docs_path}/.ai-context/")
    has_gherkin   = glob(f"{docs_path}/docs/tests/*.feature")
    has_adr       = len(glob(f"{docs_path}/docs/adr/*.md")) > 5
    has_sparc_arch = exists(f"{docs_path}/Architecture.md")
    has_sparc_sol  = exists(f"{docs_path}/Solution_Strategy.md")

    if has_ddd and has_ai_context:
        return "IDEA2PRD_FULL"      # Complete idea2prd-manual output
    elif has_ddd or has_adr:
        return "IDEA2PRD_PARTIAL"   # Partial idea2prd output
    elif has_sparc_arch and has_sparc_sol:
        return "SPARC"              # Full SPARC documentation set
    elif has_sparc_arch:
        return "SPARC_MINIMAL"      # Architecture.md only
    else:
        return "MINIMAL"            # Basic PRD only, or mixed
```

| Pipeline | Minimum Docs | Typical File Count |
|----------|-------------|-------------------|
| IDEA2PRD_FULL | `docs/ddd/` + `.ai-context/` | 30-50 files |
| IDEA2PRD_PARTIAL | `docs/ddd/` or `docs/adr/` (>5) | 15-30 files |
| SPARC | `Architecture.md` + `Solution_Strategy.md` | 8-11 files |
| SPARC_MINIMAL | `Architecture.md` only | 2-5 files |
| MINIMAL | PRD.md only | 1-3 files |

### Step 3: Detect Project Characteristics

Scan detected documents for four characteristic flags. These drive conditional
generation in later modules.

#### 3a. `has_external_apis`

```
SCAN Architecture.md, Specification.md, ADR-*-integration.md,
     context-map.md, repositories/*.md FOR:
  keywords: "API", "integration", "external", "REST", "GraphQL",
            "webhook", "third-party", "OAuth", "Stripe", "Twilio",
            "SendGrid", "OpenAI", "payment", "SMS"

IF any keyword found → has_external_apis = true
```

#### 3b. `has_database`

```
SCAN Architecture.md, Specification.md, docker-compose.yml,
     ADR-*-data.md, repositories/*.md FOR:
  keywords: "PostgreSQL", "Postgres", "MongoDB", "MySQL", "Redis",
            "database", "Prisma", "TypeORM", "Drizzle", "Knex",
            "migration", "schema", "SQLite"

IF any keyword found → has_database = true
ALSO EXTRACT: db_type (postgres|mongo|mysql|redis|sqlite)
              orm_name (prisma|typeorm|drizzle|knex|raw)
```

#### 3c. `monorepo_packages`

```
SCAN Architecture.md FOR:
  - Monorepo structure section
  - packages/ or apps/ directory listings
  - Workspace configuration references

EXTRACT: list of package names and paths
  e.g. ["packages/shared", "packages/backend", "packages/frontend"]

IF structure mentions single app (e.g. "Next.js app") →
  monorepo_packages = ["apps/web"] or similar minimal list
```

#### 3d. `docker_services`

```
SCAN Architecture.md, docker-compose.yml, Completion.md FOR:
  - Docker Compose service definitions
  - Service names and ports

EXTRACT: list of service names
  e.g. ["frontend", "backend", "postgres", "redis"]
```

### Step 4: Build Internal Project Model (IPM)

Assemble all detection results into a structured IPM object:

```
IPM = {
  pipeline_type: "SPARC" | "SPARC_MINIMAL" | "IDEA2PRD_FULL" |
                 "IDEA2PRD_PARTIAL" | "MINIMAL",

  detected_docs: {
    sparc: {
      prd:              path | null,
      solution_strategy: path | null,
      specification:    path | null,
      pseudocode:       path | null,
      architecture:     path | null,
      refinement:       path | null,
      completion:       path | null,
      research_findings: path | null,
      final_summary:    path | null,
      claude_md:        path | null
    },
    idea2prd: {
      prd:              path | null,
      ddd_strategic:    [paths] | [],
      ddd_tactical: {
        aggregates:     [paths] | [],
        entities:       [paths] | [],
        value_objects:  [paths] | [],
        events:         [paths] | [],
        repositories:   [paths] | []
      },
      adrs:             [paths] | [],
      c4_diagrams:      [paths] | [],
      pseudocode:       [paths] | [],
      gherkin_tests:    [paths] | [],
      fitness:          [paths] | [],
      completion:       path | null
    },
    ai_context: {
      readme:           path | null,
      architecture:     path | null,
      key_decisions:    path | null,
      domain_glossary:  path | null,
      bounded_contexts: path | null,
      coding_standards: path | null,
      fitness_rules:    path | null,
      pseudocode_index: path | null
    }
  },

  project_characteristics: {
    has_external_apis:  bool,
    has_database:       bool,
    db_type:            string | null,
    orm_name:           string | null,
    monorepo_packages:  [string],
    docker_services:    [string],

    // Derived flags (computed from detected_docs)
    has_ddd:            bool,   // detected_docs.idea2prd.ddd_strategic non-empty
    has_ddd_strategic:  bool,   // same as has_ddd (alias for readability)
    has_gherkin:        bool,   // detected_docs.idea2prd.gherkin_tests non-empty
    has_fitness:        bool,   // detected_docs.idea2prd.fitness non-empty
    has_adr:            bool,   // detected_docs.idea2prd.adr length > 0
    has_c4:             bool,   // detected_docs.idea2prd.c4 non-empty
    has_ai_context:     bool,   // detected_docs.ai_context.readme non-null
    has_pseudocode:     bool,   // detected_docs.sparc.pseudocode OR idea2prd.pseudocode non-null
    has_authentication: bool    // keywords "auth", "login", "JWT", "OAuth" found in docs
  },

  metadata: {
    total_docs_found:   int,
    scan_timestamp:     ISO-8601 string,
    docs_path:          string
  }
}
```

### Step 5: MANUAL Mode Checkpoint (optional)

In MANUAL mode, present the detection results for user review:

```
================================================================
CHECKPOINT 1: Document Detection Review
================================================================

Pipeline Detected: SPARC
Documents Found: 11 files

SPARC Documents:
  [x] PRD.md                    docs/PRD.md
  [x] Solution_Strategy.md      docs/Solution_Strategy.md
  [x] Specification.md          docs/Specification.md
  [x] Pseudocode.md             docs/Pseudocode.md
  [x] Architecture.md           docs/Architecture.md
  [x] Refinement.md             docs/Refinement.md
  [x] Completion.md             docs/Completion.md
  [x] Research_Findings.md      docs/Research_Findings.md
  [x] Final_Summary.md          docs/Final_Summary.md
  [ ] CLAUDE.md                 (not found)

Project Characteristics:
  has_external_apis:  true   (found: "Stripe", "OpenAI" in Architecture.md)
  has_ddd:            false  (no docs/ddd/ found)
  has_authentication: true   (found: "JWT", "OAuth" in Specification.md)
  has_database:       true   (PostgreSQL via Prisma)
  monorepo_packages:  packages/shared, packages/backend, packages/frontend
  docker_services:    frontend, backend, postgres

Commands: "ok" to proceed | "add [doc]" | "remove [doc]"
================================================================
```

Wait for user confirmation before passing IPM to Module 02.

---

## Output

| Field | Type | Description |
|-------|------|-------------|
| `ipm` | IPM object | Complete Internal Project Model as defined in Step 4 |

The IPM is the sole output of this module. It is consumed by:
- **Module 02 (Analyze & Map)** -- to determine scoring rules and instrument mapping
- **Module 03 (Generate P0)** -- to select conditional P0 items and fill templates
- **Module 04+ (Generate P1-P3)** -- to select optional instruments

---

## Quality Gate

All of the following must be satisfied before the IPM is considered valid:

| Check | Condition | Action on Failure |
|-------|-----------|-------------------|
| Minimum docs | SPARC: at least `PRD.md` + `Architecture.md` present | Halt. Ask user to upload missing docs. |
| Minimum docs | idea2prd: at least `docs/ddd/` directory present | Halt. Ask user to upload missing docs. |
| Pipeline resolved | `pipeline_type` is not ambiguous | If mixed signals, default to "SPARC" with unified mapping. |
| Characteristics scanned | All 4 characteristic flags have been evaluated | Re-scan if any flag is missing. |
| Paths valid | Every path in `detected_docs` points to an existing file | Remove invalid paths, log warnings. |
| Total docs > 0 | `metadata.total_docs_found` > 0 | Halt. No documents to process. |

---

## Dependencies

None. This is the foundation module with no upstream dependencies.

Files read during execution are the user's uploaded documentation, not skill
reference files.

---

## Reusability

This module can be reused by **any skill that needs to detect documentation type
and build a project model**, including:

- **Pipeline validation tools** that need to verify doc completeness
- **Documentation generators** that need to know what source material exists
- **Project analysis skills** that need to classify project type
- **Migration tools** that convert between documentation formats (e.g. SPARC to idea2prd)

The detection logic (Step 2) and characteristic scanning (Step 3) are
independent of the toolkit generator and can operate standalone. The IPM
schema (Step 4) serves as a universal interchange format for project metadata.

To reuse only the detection logic without the full IPM build:
1. Run Steps 1-2 to get `pipeline_type`
2. Optionally run Step 3 for characteristic flags
3. Skip Step 4 if the full IPM structure is not needed
