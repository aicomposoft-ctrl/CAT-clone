# Module: Cross-Project Learning

Enable toolkit generation to learn from previous projects' harvested artifacts.
When generating a new toolkit, this module checks a cross-project artifact registry
for proven patterns, battle-tested rules, and validated templates that match the
new project's characteristics, then injects them into the appropriate generation phase.

## Input

| Parameter | Type | Description | Required |
|-----------|------|-------------|----------|
| `project_ipm` | Object | Internal Project Model from Module 01 (tech stack, architecture, domain, features) | YES |
| `artifact_registry_path` | Path | Cross-project artifact registry (default: `.claude/skills/knowledge-extractor/registry/`) | NO |
| `maturity_model` | Reference | `view() knowledge-extractor/references/maturity-model.md` | YES |
| `artifact_categories` | Reference | `view() knowledge-extractor/references/artifact-categories.md` | YES |
| `minimum_relevance_score` | Number | Minimum relevance score for auto-include (default: 70) | NO |
| `minimum_maturity_for_auto` | Level | Minimum maturity for auto-include (default: Beta) | NO |

### Internal Project Model (IPM) Structure

The IPM is produced by Module 01 (Detect & Parse). Relevant fields for matching:

```json
{
  "project_name": "{{PROJECT_NAME}}",
  "tech_stack": {
    "languages": ["{{LANG_1}}", "{{LANG_2}}"],
    "frameworks": ["{{FW_1}}", "{{FW_2}}"],
    "databases": ["{{DB_1}}"],
    "infrastructure": ["{{INFRA_1}}"]
  },
  "architecture_type": "{{MONOLITH|MICROSERVICES|SERVERLESS|MONOREPO}}",
  "domain": "{{DOMAIN_KEYWORD}}",
  "has_external_apis": {{BOOLEAN}},
  "has_database": {{BOOLEAN}},
  "has_authentication": {{BOOLEAN}},
  "docker_services": ["{{SERVICE_1}}", "{{SERVICE_2}}"],
  "detected_pipeline": "{{SPARC|IDEA2PRD|MIXED}}"
}
```

## Process

### Step 1: Scan Cross-Project Artifact Registry

Locate and load the artifact registry:

```
SCAN locations in priority order:
  1. {{artifact_registry_path}} (explicit parameter)
  2. .claude/skills/knowledge-extractor/registry/
  3. .claude/toolkit-manifest.json
  4. docs/harvest-report-*.md (parse individual reports)
```

**Registry Format (if `registry/` directory exists):**

```
registry/
├── index.json                    # Master artifact index
├── skills/
│   ├── {{artifact-name}}.json    # Artifact metadata
│   └── ...
├── patterns/
│   ├── {{artifact-name}}.json
│   └── ...
├── rules/
│   ├── {{artifact-name}}.json
│   └── ...
├── templates/
│   ├── {{artifact-name}}.json
│   └── ...
├── commands/
│   ├── {{artifact-name}}.json
│   └── ...
├── snippets/
│   ├── {{artifact-name}}.json
│   └── ...
└── hooks/
    ├── {{artifact-name}}.json
    └── ...
```

**Artifact Metadata Format:**

```json
{
  "name": "{{ARTIFACT_NAME}}",
  "category": "{{CATEGORY}}",
  "maturity": "{{ALPHA|BETA|STABLE|PROVEN}}",
  "version": "v{{MAJOR}}.{{MINOR}}",
  "description": "{{DESCRIPTION}}",
  "source_projects": ["{{PROJECT_1}}", "{{PROJECT_2}}"],
  "extracted": "{{DATE}}",
  "last_updated": "{{DATE}}",
  "characteristics": {
    "tech_stacks": ["{{STACK_1}}", "{{STACK_2}}", "*"],
    "architecture_types": ["{{TYPE_1}}", "*"],
    "domains": ["{{DOMAIN_1}}", "*"],
    "requires_database": {{BOOLEAN|NULL}},
    "requires_external_apis": {{BOOLEAN|NULL}},
    "requires_authentication": {{BOOLEAN|NULL}}
  },
  "tags": ["{{TAG_1}}", "{{TAG_2}}"],
  "artifact_path": "{{PATH_TO_ARTIFACT_FILE}}",
  "usage_count": {{N}},
  "feedback_score": {{0-100|NULL}}
}
```

If no registry exists, report:
```
No cross-project artifact registry found.
Proceeding with standard toolkit generation (no cross-project learning).
Tip: Run /harvest on completed projects to build the registry over time.
```

### Step 2: Match Project Characteristics Against Artifact Metadata

For each artifact in the registry, compute a relevance score based on how well
its characteristics match the new project's IPM:

**Matching Dimensions:**

| Dimension | Weight | Matching Logic |
|-----------|--------|----------------|
| Tech Stack | 30 | Language/framework overlap percentage |
| Architecture Type | 20 | Exact match = full score, related match = half |
| Domain | 15 | Exact match = full, related = half, wildcard = quarter |
| Infrastructure Match | 10 | Database/Docker/API overlap |
| Maturity Level | 15 | Proven=15, Stable=12, Beta=8, Alpha=3 |
| Usage Count | 10 | Logarithmic: log2(usage_count + 1) * 10/5, capped at 10 |

**Relevance Score Formula:**

```
FUNCTION compute_relevance(artifact, project_ipm):
  score = 0

  # Tech Stack Match (0-30 points)
  artifact_stacks = artifact.characteristics.tech_stacks
  IF "*" IN artifact_stacks:
    stack_score = 25  # Universal gets high but not full score
  ELSE:
    overlap = intersection(artifact_stacks, project_ipm.tech_stack.all())
    total = union(artifact_stacks, project_ipm.tech_stack.all())
    stack_score = (len(overlap) / max(len(total), 1)) * 30
  score += stack_score

  # Architecture Type Match (0-20 points)
  IF artifact.characteristics.architecture_types contains "*":
    score += 16
  ELIF project_ipm.architecture_type IN artifact.characteristics.architecture_types:
    score += 20
  ELIF architecture_is_related(project_ipm.architecture_type, artifact.characteristics):
    score += 10

  # Domain Match (0-15 points)
  IF artifact.characteristics.domains contains "*":
    score += 4   # Universal domain artifacts get minimal domain score
  ELIF project_ipm.domain IN artifact.characteristics.domains:
    score += 15
  ELIF domain_is_related(project_ipm.domain, artifact.characteristics.domains):
    score += 8

  # Infrastructure Match (0-10 points)
  infra_checks = [
    (artifact.requires_database, project_ipm.has_database),
    (artifact.requires_external_apis, project_ipm.has_external_apis),
    (artifact.requires_authentication, project_ipm.has_authentication)
  ]
  FOR each (artifact_req, project_has) IN infra_checks:
    IF artifact_req == NULL:
      score += 3  # No requirement = compatible
    ELIF artifact_req == project_has:
      score += 3  # Match
    # Mismatch: no points (but not blocking)

  # Maturity Level (0-15 points)
  maturity_scores = {PROVEN: 15, STABLE: 12, BETA: 8, ALPHA: 3}
  score += maturity_scores[artifact.maturity]

  # Usage Count (0-10 points)
  score += min(log2(artifact.usage_count + 1) * 2, 10)

  RETURN round(score)  # 0-100
```

### Step 3: Score and Rank Artifacts

Sort all artifacts by relevance score and prepare the ranked list:

```markdown
## Artifact Relevance Ranking

| Rank | Artifact | Category | Maturity | Relevance | Matching Dimensions |
|------|----------|----------|----------|-----------|---------------------|
| 1 | {{NAME}} | {{CAT}} | {{LEVEL}} | {{SCORE}}/100 | Stack: {{X}}, Arch: {{Y}}, Domain: {{Z}} |
| 2 | {{NAME}} | {{CAT}} | {{LEVEL}} | {{SCORE}}/100 | Stack: {{X}}, Arch: {{Y}}, Domain: {{Z}} |
```

### Step 4: Filter by Maturity Level

Apply maturity-based filtering rules from the maturity model:

| Maturity Level | Symbol | Auto-Include Threshold | Action |
|----------------|--------|------------------------|--------|
| Proven | *** | Relevance >= 50 | Auto-include in P0 generation |
| Stable | *** | Relevance >= 60 | Auto-include in P1 generation |
| Beta | *** | Relevance >= 70 | Recommend in P2, include with user confirmation |
| Alpha | *** | N/A (never auto) | Mention in report only, never auto-include |

**Filter Logic:**

```
FOR each artifact IN ranked_artifacts:
  IF artifact.maturity == PROVEN AND relevance >= 50:
    → INJECT into P0 (mandatory items)
  ELIF artifact.maturity == STABLE AND relevance >= 60:
    → INJECT into P1 (recommended items)
  ELIF artifact.maturity == BETA AND relevance >= 70:
    → RECOMMEND in P2 (optional items, user confirms)
  ELIF artifact.maturity == ALPHA:
    → REPORT only (mention in cross-project learning report)
  ELSE:
    → SKIP (relevance too low for maturity level)
```

### Step 5: Inject Matched Artifacts into Toolkit Generation

For each artifact that passed the filter, determine the injection target
within the toolkit generator's output:

**Injection Targets by Category:**

| Artifact Category | P0 Injection Target | P1 Injection Target |
|-------------------|---------------------|---------------------|
| Skills | Copy to `.claude/skills/`, add to CLAUDE.md skills table | Add as recommended skill |
| Commands | Add to `.claude/commands/`, reference in CLAUDE.md | Add as recommended command |
| Hooks | Merge into `settings.json` hooks | Add as recommended hook |
| Rules | Add to `.claude/rules/`, reference in CLAUDE.md | Add as recommended rule |
| Templates | Use as improved default for scaffold generation | Suggest as alternative template |
| Patterns | Embed in `project-context/` skill, reference in architect agent | Add to knowledge base |
| Snippets | Include in `coding-standards/` skill | Add to utility references |

**Injection Protocol:**

```
FOR each injected_artifact:
  1. READ artifact content from artifact_path
  2. VERIFY artifact has been decontextualized (no project-specific references)
  3. DETERMINE injection target based on category + generation phase
  4. IF category == "skill":
     → Use Module 08 (Skill Composition) for copy + path rewrite
  5. IF category == "rule":
     → Append to existing rule file or create new rule in .claude/rules/
  6. IF category == "template":
     → Replace or supplement default template in generation
  7. IF category == "pattern":
     → Add to project-context/ or architect agent references
  8. RECORD injection in usage tracking
```

### Step 6: Track Usage for Maturity Promotion

Every injected artifact gets a usage record for future maturity assessment:

```json
{
  "artifact_name": "{{ARTIFACT_NAME}}",
  "used_in_project": "{{PROJECT_NAME}}",
  "used_at": "{{DATE}}",
  "injection_phase": "{{P0|P1|P2}}",
  "injection_target": "{{TARGET_PATH}}",
  "relevance_score": {{SCORE}},
  "outcome": "{{PENDING|SUCCESS|REMOVED}}"
}
```

**Usage Tracking File:** `{{artifact_registry_path}}/usage-log.jsonl`

Each line is a JSON object (JSON Lines format for append-only writes).

**Maturity Promotion Triggers:**

After recording usage, check if any artifact qualifies for promotion:

```
FOR each artifact WITH new usage record:
  current_usage_count = count_unique_projects(artifact.name, usage_log)

  IF artifact.maturity == ALPHA AND current_usage_count >= 2:
    → RECOMMEND promotion to Beta
    → CHECK: at least 1 edge case handled, "When NOT to use" documented
  IF artifact.maturity == BETA AND current_usage_count >= 3:
    → RECOMMEND promotion to Stable
    → CHECK: multiple variants documented, no open issues
  IF artifact.maturity == STABLE AND current_usage_count >= 5:
    → RECOMMEND promotion to Proven
    → CHECK: exemplary docs, community consensus

  # Promotions are RECOMMENDATIONS, not automatic
  # Add to output report for user review
```

## Output

### 1. Cross-Project Learning Report

```markdown
# Cross-Project Learning Report: {{PROJECT_NAME}}
Date: {{DATE}}

## Project Characteristics (from IPM)
- Tech Stack: {{LANGUAGES}}, {{FRAMEWORKS}}
- Architecture: {{ARCHITECTURE_TYPE}}
- Domain: {{DOMAIN}}
- Database: {{YES/NO}} | External APIs: {{YES/NO}} | Auth: {{YES/NO}}

## Registry Summary
- Total artifacts scanned: {{N}}
- Artifacts matched (relevance >= 50): {{M}}
- Artifacts injected: {{K}}
- Artifacts recommended: {{R}}
- Artifacts reported only: {{A}}

## Injected Artifacts (Auto-Included)

### P0 — Mandatory (Proven artifacts, relevance >= 50)

| # | Artifact | Category | Relevance | Injection Target | Source Projects |
|---|----------|----------|-----------|------------------|-----------------|
| 1 | {{NAME}} | {{CAT}} | {{SCORE}} | {{TARGET}} | {{PROJECTS}} |

### P1 — Recommended (Stable artifacts, relevance >= 60)

| # | Artifact | Category | Relevance | Injection Target | Source Projects |
|---|----------|----------|-----------|------------------|-----------------|
| 1 | {{NAME}} | {{CAT}} | {{SCORE}} | {{TARGET}} | {{PROJECTS}} |

### P2 — Suggested (Beta artifacts, relevance >= 70)

| # | Artifact | Category | Relevance | Injection Target | User Action |
|---|----------|----------|-----------|------------------|-------------|
| 1 | {{NAME}} | {{CAT}} | {{SCORE}} | {{TARGET}} | Confirm to include |

## Report Only (Alpha artifacts — for awareness)

| # | Artifact | Category | Relevance | Why Not Auto-Included |
|---|----------|----------|-----------|------------------------|
| 1 | {{NAME}} | {{CAT}} | {{SCORE}} | Alpha maturity — needs validation in more projects |

## Maturity Promotion Candidates

| Artifact | Current | Proposed | Usage Count | Missing Criteria |
|----------|---------|----------|-------------|------------------|
| {{NAME}} | {{CURRENT}} | {{PROPOSED}} | {{COUNT}} | {{MISSING}} |

## Skipped Artifacts (Low Relevance)

| Artifact | Relevance | Reason |
|----------|-----------|--------|
| {{NAME}} | {{SCORE}} | {{REASON}} |
```

### 2. Usage Tracking Records

Appended to `{{artifact_registry_path}}/usage-log.jsonl`.

### 3. Modified Generation Output

Artifacts injected into the toolkit generator's output at their respective
phase targets (P0, P1, P2).

## Quality Gate

| Check | Threshold | Blocking? |
|-------|-----------|-----------|
| No Alpha artifacts auto-included | 0 Alpha in P0/P1 | YES |
| Relevance score >= 70 for Beta auto-include | Minimum 70 | YES |
| Relevance score >= 60 for Stable auto-include | Minimum 60 | YES |
| Relevance score >= 50 for Proven auto-include | Minimum 50 | YES |
| All injected artifacts pass decontextualization check | No project-specific references | YES |
| Usage tracking record created for each injection | 100% tracked | YES |
| Maturity promotions follow promotion criteria | All criteria checked | YES (for promotions) |
| No duplicate artifacts injected (same artifact twice) | 0 duplicates | YES |
| Injection targets exist in generation plan | All targets valid | YES |

**Validation Sequence:**

```
1. VERIFY no Alpha artifacts in auto-include lists
2. VERIFY all relevance scores meet maturity-specific thresholds
3. FOR each injected artifact:
   a. GREP for project-specific references (company names, URLs, credentials)
   b. VERIFY injection target exists in the generation plan
   c. VERIFY no naming conflicts with existing generated artifacts
4. VERIFY usage-log.jsonl is append-only (no overwrites)
5. VERIFY promotion candidates meet ALL criteria from maturity-model.md
```

## Dependencies

| Dependency | Purpose | Fallback |
|------------|---------|----------|
| `view() knowledge-extractor/references/maturity-model.md` | Maturity level definitions, promotion criteria, trust levels | Use inline maturity table: Alpha (first use) / Beta (2+ projects) / Stable (3+ projects) / Proven (5+ projects, exemplary) |
| `view() knowledge-extractor/references/artifact-categories.md` | Category definitions for injection target mapping | Use inline category list: Skills, Commands, Hooks, Rules, Templates, Patterns, Snippets |
| Module 01 (Detect & Parse) | Provides IPM for project characteristic matching | Require user to provide tech stack and architecture manually |
| Module 08 (Skill Composition) | Copy and rewrite skills that are injected from the registry | Copy skills manually with path substitution |

## Reusability

The cross-project learning pattern is **universal** for any AI pipeline that generates
output from templates. The core insight is: **previous outputs improve future generation**.

**Pattern: Registry-Scored-Injection**

```
[Previous Projects] → [Harvest/Extract] → [Artifact Registry]
                                                 ↓
                                           [Score & Match]
                                                 ↓
[New Project IPM] → [Filter by Maturity] → [Inject into Generation]
                                                 ↓
                                           [Track Usage]
                                                 ↓
                                           [Promote Maturity]
```

**Reuse scenarios:**

| Scenario | Adaptation |
|----------|------------|
| CI/CD pipeline generator | Match project characteristics against pipeline artifact registry |
| Infrastructure-as-Code generator | Match cloud provider + scale against infra pattern registry |
| API scaffolder | Match API style + auth requirements against API pattern registry |
| Documentation generator | Match doc style + audience against documentation template registry |
| Test framework configurator | Match test strategy + tech stack against testing pattern registry |
| AI prompt library | Match task type + domain against prompt template registry |

**To adapt for a different pipeline:**

1. Define your equivalent of the IPM (project characteristics model)
2. Define your equivalent of the artifact registry (stored outputs from previous runs)
3. Implement the relevance scoring function with weights appropriate to your domain
4. Map your artifact categories to injection targets in your generation pipeline
5. Keep the maturity model, usage tracking, and promotion logic unchanged

**Key design decisions:**

- Relevance scoring is **weighted multi-dimensional**, not binary match/no-match,
  because partial matches are often valuable (a pattern from a similar but not identical
  stack is still useful)
- Alpha artifacts are **never auto-included** because untested artifacts in generated
  toolkits create unpredictable downstream issues
- Usage tracking uses **append-only JSON Lines** for simplicity and crash safety
- Maturity promotions are **recommendations**, not automatic, because promotion criteria
  include qualitative checks (documentation quality, edge case handling) that require
  human or AI judgment
- The registry is **file-based** (not a database) for portability across development
  environments and compatibility with version control
