# Module: Analyze & Map

Phase 2 of the CC-Toolkit-Generator Enhanced pipeline.
Takes the Internal Project Model (IPM) from Module 01, maps documents to toolkit
instruments using pipeline-specific rules and a scoring engine, and produces a
prioritized Instrument Map.

---

## Input

| Parameter | Type | Source |
|-----------|------|--------|
| `ipm` | IPM object | Output of Module 01 (Detect & Parse) |

The IPM must contain at minimum:
- `pipeline_type` -- determines which mapping table to apply
- `detected_docs` -- documents to map to instruments
- `project_characteristics` -- flags for conditional instruments

---

## Process

### Step 1: Select Mapping Table

Based on `ipm.pipeline_type`, load the appropriate mapping rules.

```
IF pipeline_type IN ["SPARC", "SPARC_MINIMAL"]:
    USE sparc_mapping (defined below)
ELIF pipeline_type IN ["IDEA2PRD_FULL", "IDEA2PRD_PARTIAL"]:
    USE idea2prd_mapping
    view() references/extended-mapping.md   # Complete DDD/ADR/Gherkin/Fitness mappings
ELIF pipeline_type == "MINIMAL":
    USE sparc_mapping with reduced scope
```

### Step 2: Apply SPARC Mapping

When pipeline is SPARC or SPARC_MINIMAL, map documents to instruments using
the primary SPARC mapping table:

```
SPARC DOCUMENT MAPPING:

PRD.md:
  - Executive Summary    → CLAUDE.md Overview (P0)
  - Problem Statement    → CLAUDE.md Problem Context (P0), architect.md (P1)
  - Functional Reqs      → /plan features (P1), /start Phase 2 scope
  - NFRs                 → security.md (P0), testing.md (P1)
  - User Stories         → /test templates (P1), testing-patterns/ (P1)

Solution_Strategy.md:
  - Root Cause/Framework → project-context/ (P1), architect.md (P1), CLAUDE.md

Specification.md:
  - Data Model/API/Security → /start Phase 2 (P0), security.md (P0), coding-standards/ (P1)

Pseudocode.md:
  - Algorithms/Error Handling → planner.md (P1), code-reviewer.md (P1), /start refs

Architecture.md:
  - Structure/Stack/Docker/APIs → CLAUDE.md (P0), /start (P0), .mcp.json (P3), coding-style.md (P0)

Refinement.md:
  - Edge Cases/Testing/Security → code-reviewer.md (P1), testing.md (P1), /test (P1), tdd-guide.md (P2)

Completion.md:
  - CI/CD/Docker/Monitoring → /deploy (P1), /start Phase 3, hooks (P2)

Research_Findings.md:
  - Tech Decisions/Best Practices → architect.md (P1), coding-standards/ (P1), CLAUDE.md

Final_Summary.md:
  - Quick Reference → CLAUDE.md (P0), DEVELOPMENT_GUIDE.md (P0)
```

Extraction patterns for SPARC documents:

```
EXTRACT PRD.md:
  name        → title
  problem     → context
  requirements → features
  NFRs        → rules

EXTRACT Architecture.md:
  structure   → /start P1
  packages    → /start P2
  docker      → /start P3
  stack       → CLAUDE.md
  APIs        → security-patterns
  DB          → migration

EXTRACT Pseudocode.md:
  functions   → planner templates
  algorithms  → /start P2 refs
  errors      → code-reviewer
```

### Step 3: Apply idea2prd Mapping

When pipeline is IDEA2PRD_FULL or IDEA2PRD_PARTIAL, apply the extended mapping.
Read `view() references/extended-mapping.md` for the complete mapping matrix.

Key idea2prd-specific mappings:

```
DDD STRATEGIC:
  bounded-contexts.md:
    - Context definitions       → domain-expert.md agent (P1)
    - Context responsibilities  → Agent scope definitions
    - Ubiquitous Language       → domain-glossary rule, project-context/ (P1)
  context-map.md:
    - Relationships            → Integration hooks
    - Anti-Corruption Layer    → Validation hooks, security.md

DDD TACTICAL:
  aggregates/*.md:
    - Aggregate Root           → ddd-validator.md agent (P1)
    - Invariants               → PreToolUse validation hooks (P2)
    - Business Rules           → coding-style.md (P0), validation hooks
  entities/*.md:
    - Entity definitions       → Type checking hooks
  events/*.md:
    - Domain Events            → event-handlers/ skill (P1)
    - Event handlers           → PostToolUse hooks (P2)

ADR DOCUMENTS:
  FOR EACH adr/*.md:
    CLASSIFY by keywords:
      "security", "auth", "encryption"  → security.md rule
      "performance", "scale", "cache"   → performance rules
      "test", "coverage", "TDD"         → testing.md rule
      "API", "REST", "GraphQL"          → api-patterns/ skill
      "database", "storage"             → data rules
      technology names                  → coding-standards/ skill

C4 DIAGRAMS:
  context.mermaid   → CLAUDE.md overview, architect.md context
  container.mermaid → CLAUDE.md structure, Agent boundaries
  component.mermaid → Skill boundaries, coding-standards/

PSEUDOCODE:
  {Aggregate}.pseudo:
    FUNCTION signature  → planner.md templates (P1)
    VALIDATE statements → PreToolUse hooks (P2)
    EMIT statements     → event-handlers/ skill (P1)
    Error handling      → code-reviewer knowledge (P1)

GHERKIN TESTS:
  *.feature:
    Feature name      → /test command scope (P1)
    Scenario          → Test templates
    Given/When/Then   → Setup/Action/Assertion patterns
    Scenario Outline  → Parameterized tests

FITNESS FUNCTIONS:
  fitness-functions.md:
    Architecture fitness → ddd-validator agent (P1)
    Code quality fitness → PostToolUse hook (P2)
    Security fitness     → PreToolUse hook (P2)

.AI-CONTEXT (8 files):
  README.md             → CLAUDE.md Overview (P0)
  architecture-summary  → CLAUDE.md Architecture (P0)
  key-decisions         → CLAUDE.md Decisions (P0)
  domain-glossary       → project-context/ skill (P1)
  bounded-contexts      → domain-model.md rule (P0)
  coding-standards      → coding-style.md rule (P0)
  fitness-rules         → fitness-functions.md rule (P1)
  pseudocode-index      → planner.md agent (P1)
```

### Step 4: Score Each Instrument

Apply the scoring engine to every candidate instrument. Read
`view() references/enhanced-recommendations.md` for detailed scoring rules.

#### 4a. Base Scores by Document Type

| Document Type | Base Score | Max Boost |
|---------------|------------|-----------|
| .ai-context/* | +15 | +5 |
| PRD.md | +10 | +5 |
| DDD Strategic | +12 | +8 |
| DDD Tactical | +10 | +10 |
| ADR (>10 files) | +10 | +5 |
| Pseudocode | +10 | +5 |
| Gherkin | +10 | +5 |
| Fitness | +8 | +5 |
| C4 | +5 | +3 |
| Completion | +5 | +3 |

#### 4b. Smart Recommendation Boosts

Apply these boosts based on document content and count:

```
# SPARC Core Boosts
Architecture.md present    → architect.md (+10), /start (+10)
Pseudocode.md present      → planner.md (+10), BOOST /start P2
Refinement.md present      → testing.md (+8), code-reviewer.md (+8), /test (+8)
Solution_Strategy present  → project-context/ (+8), BOOST architect (+3)
Completion.md present      → /deploy (+8), BOOST /start P3

# Detection-based Boosts
has_external_apis = true   → security-patterns/ (+10), secrets-management.md (+10)
has_database = true        → BOOST /start P3 with migration
"Coolify" found            → coolify MCP (+8)
"Docker" found             → docker MCP (+5)

# DDD-Specific Boosts
docs/ddd/strategic/ exists        → domain-expert.md (+10)
aggregates/ has >3 files          → ddd-validator.md (+8), +5 if >7 files
aggregates/ has >5 files          → aggregate-patterns/ (+5)
events/ has >3 files              → event-handlers/ (+5)
events/ has >0 files              → event-handlers/ (+10)
docs/adr/ has >10 files           → architect.md (+10)
docs/adr/ has >15 files           → architect.md (+5 additional)
docs/tests/*.feature exists       → testing-patterns/ (+10), tdd-guide.md (+8)
tests/ has >10 scenarios          → testing-patterns/ (+5)
docs/fitness/ exists              → fitness-functions.md (+10)
fitness has >5 functions          → validation hooks (+5)
.ai-context/ exists               → INTEGRATE into CLAUDE.md, project-context/ (+10)
.ai-context/ has >4 files         → project-context/ RECOMMEND

# ADR Security Boost
FOR EACH adr/*.md containing "security": security.md += 2
FOR EACH adr/*.md containing "authentication": security.md += 1
FOR EACH adr/*.md containing "encryption": security.md += 1
```

#### 4c. Assign Priority Tiers

```python
def assign_tier(score: int, document_source: str) -> str:
    # Source-specific boosts
    ddd_boost        = 2 if document_source in ["DDD_STRATEGIC", "DDD_TACTICAL"] else 0
    gherkin_boost    = 2 if document_source == "GHERKIN" else 0
    ai_context_boost = 3 if document_source == "AI_CONTEXT" else 0

    adjusted_score = score + ddd_boost + gherkin_boost + ai_context_boost

    if adjusted_score >= 18:
        return "P1"   # Highly recommended, default ON
    elif adjusted_score >= 12:
        return "P1"   # Recommended, default ON
    elif adjusted_score >= 8:
        return "P2"   # Optional, default OFF
    else:
        return "P3"   # External/advanced, default OFF
```

Note: P0 items are **not scored** -- they are always mandatory regardless of
score. P0 assignment is hardcoded in Module 03.

### Step 5: Build Instrument Map

Assemble all scored instruments into the Instrument Map, sorted by tier then
by score descending:

```
instrument_map = {
  p0_mandatory: [
    # Always generated -- not scored, hardcoded list
    # See Module 03 for the definitive P0 list
  ],

  p0_conditional: [
    # Generated IF characteristic flags are set
    { name: "secrets-management.md", type: "rule",
      condition: "has_external_apis", source_docs: [...] },
    { name: "security-patterns/", type: "skill",
      condition: "has_external_apis", source_docs: [...] },
    { name: "domain-model.md", type: "rule",
      condition: "has_ddd_strategic", source_docs: [...] }
  ],

  p1_recommended: [
    # Scored instruments with tier P1 (score >= 12)
    { name: "planner.md", type: "agent", score: 21,
      source_docs: ["Pseudocode.md"], pipeline: "SPARC" },
    { name: "code-reviewer.md", type: "agent", score: 19,
      source_docs: ["Refinement.md", "Specification.md"], pipeline: "SPARC" },
    { name: "architect.md", type: "agent", score: 18,
      source_docs: ["Architecture.md", "Solution_Strategy.md"], pipeline: "SPARC" },
    # ... more P1 instruments sorted by score
  ],

  p2_optional: [
    # Scored instruments with tier P2 (score 8-11)
    { name: "tdd-guide.md", type: "agent", score: 10,
      source_docs: [...], pipeline: "SPARC" },
    # ... more P2 instruments
  ],

  p3_external: [
    # Scored instruments with tier P3 (score < 8)
    { name: ".mcp.json", type: "config", score: 5,
      source_docs: [...] }
  ],

  enterprise_lifecycle: {
    # Included IF DDD detected -- see references/templates/feature-lifecycle-ent.md
    enabled: bool,
    items: [
      { name: "/feature-ent", type: "command" },
      { name: "feature-lifecycle-ent.md", type: "rule" },
      { name: "idea2prd-manual/", type: "skill", action: "copy+rewrite" },
      { name: "goap-research-ed25519/", type: "skill", action: "copy+rewrite" }
    ]
  },

  feature_suggestions: {
    # Always included at P1 -- see references/templates/feature-suggestions.md
    items: [
      { name: "/next", type: "command" },
      { name: "feature-navigator/", type: "skill" },
      { name: "feature-roadmap.json", type: "config" },
      { name: "feature-context.py", type: "hook" }
    ]
  },

  automation: {
    # Always included at P1 -- see references/templates/automation-commands.md
    items: [
      { name: "/go", type: "command" },
      { name: "/run", type: "command" },
      { name: "/docs", type: "command" }
    ]
  }
}
```

### Step 6: MANUAL/HYBRID Mode Checkpoint (conditional)

In HYBRID mode, present a summary checkpoint (Checkpoint 1 in HYBRID,
Checkpoint 2 in MANUAL):

```
================================================================
CHECKPOINT: Smart Selection
================================================================

Pipeline Detected: [pipeline_type]
Documents Found: [total] files across [categories] categories

P0 Generated (mandatory):
  - CLAUDE.md                              [size estimate]
  - security.md                            [size estimate]
  - coding-style.md                        [size estimate]
  [IF has_ddd_strategic:]
  - domain-model.md (from DDD Strategic)   [size estimate]
  [IF has_external_apis:]
  - secrets-management.md                  [size estimate]
  - security-patterns/                     [size estimate]

P1 Recommended (score >= 12):
  | # | Instrument       | Type    | Score | Source              |
  |---|------------------|---------|-------|---------------------|
  | 1 | [name]           | [type]  | [N]   | [source docs]       |
  | 2 | ...              | ...     | ...   | ...                 |

P2 Optional (score 8-11):
  | # | Instrument       | Type    | Score | Source              |
  ...

P3 External:
  | # | Instrument       | Type    | Score | Source              |
  ...

Quick Actions:
  "ok"       -- generate all P1 ([N] instruments)
  "minimum"  -- P0 only
  "maximum"  -- all P1 + P2 + P3 ([N] instruments)
  "+ddd"     -- add all DDD-specific
  "+gherkin" -- add all Gherkin-specific
  "+N" / "-N" -- toggle specific instrument by number

================================================================
```

Wait for user selection before passing Instrument Map to Module 03.

---

## Output

| Field | Type | Description |
|-------|------|-------------|
| `instrument_map` | InstrumentMap object | Scored, tiered list of all toolkit instruments as defined in Step 5 |

The Instrument Map is consumed by:
- **Module 03 (Generate P0)** -- uses `p0_mandatory` and `p0_conditional` lists
- **Module 04 (Generate P1)** -- uses `p1_recommended`, `enterprise_lifecycle`, `feature_suggestions`, `automation`
- **Module 05 (Generate P2-P3)** -- uses `p2_optional` and `p3_external`
- **Module 06 (Package)** -- uses the full map for validation checklist

---

## Quality Gate

| Check | Condition | Action on Failure |
|-------|-----------|-------------------|
| All P0 items have sources | Every P0 mandatory item has at least one `source_doc` mapped from the IPM | Review IPM; if doc genuinely missing, generate P0 item from available context with degraded quality warning. |
| No orphan docs | Every document in `ipm.detected_docs` maps to at least one instrument | Log warning for unmapped docs. Not blocking but indicates potential content loss. |
| Score consistency | No P1 item has score < 12; no P2 item has score >= 12 | Re-run tier assignment on failing items. |
| Conditional P0 flags match | `p0_conditional` items match `project_characteristics` flags | Remove conditional items whose flags are false. |
| Instrument Map non-empty | At least P0 mandatory items are present | Always true by construction (P0 is hardcoded). |

---

## Dependencies

This module reads the following reference files during execution:

| Reference | Purpose | When Read |
|-----------|---------|-----------|
| `view() references/enhanced-recommendations.md` | Detailed scoring rules for DDD, ADR, Gherkin, Fitness, Pseudocode, .ai-context documents | Step 4 (scoring engine) |
| `view() references/extended-mapping.md` | Complete document-to-instrument mapping for idea2prd pipeline | Step 3 (idea2prd mapping) |

These files are part of the cc-toolkit-generator-enhanced skill and are read
at the paths:
- `.claude/skills/cc-toolkit-generator-enhanced/references/enhanced-recommendations.md`
- `.claude/skills/cc-toolkit-generator-enhanced/references/extended-mapping.md`

---

## Reusability

The scoring engine (Steps 4a-4c) is a general-purpose component that can be
reused for **any document-to-artifact mapping problem**:

1. **Define a mapping table** (document section -> output artifact)
2. **Define base scores** per document type
3. **Define boost rules** based on content analysis
4. **Apply tier assignment** using the threshold function

This three-layer scoring model (base score + content boosts + tier thresholds)
is domain-agnostic. To adapt for a different domain:
- Replace the SPARC/idea2prd mapping tables with domain-specific mappings
- Adjust base scores to reflect domain priorities
- Define domain-specific boost conditions
- Keep the tier assignment function unchanged (or adjust thresholds)

The Instrument Map output format is also reusable as a generic "prioritized
artifact manifest" for any toolkit or scaffold generator.
