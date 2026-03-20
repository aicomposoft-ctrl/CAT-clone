# Module: Harvest Feedback

Feedback loop between knowledge extraction (/harvest) and toolkit generation.
After a project completes and /harvest extracts reusable knowledge, this module
analyzes the harvested artifacts and improves the toolkit generator's templates,
defaults, and rules for future projects.

## Input

| Source | Location | Description |
|--------|----------|-------------|
| Harvest reports | `docs/harvest-report-*.md` | Completed harvest session outputs |
| Extracted artifacts catalog | `.claude/toolkit-manifest.json` or CLAUDE.md toolkit section | Registry of all harvested artifacts with maturity levels |
| Current toolkit templates | `.claude/skills/cc-toolkit-generator-enhanced/references/templates/` | Templates used by the generator |
| Maturity model | `view() knowledge-extractor/references/maturity-model.md` | Artifact lifecycle definitions |
| Generator SKILL.md | `view() cc-toolkit-generator-enhanced/SKILL.md` | Current generation rules and recommendations |

## Process

### Step 1: Scan for Completed Harvest Reports

Locate all harvest reports in the project:

```
SCAN docs/harvest-report-*.md
SCAN docs/harvest-history/
SCAN .claude/toolkit-manifest.json
```

For each report, extract:
- **Artifact list** with categories, maturity levels, and source files
- **Skipped items** with reasons (these reveal template gaps)
- **Recommendations** section (these are explicit improvement hints)
- **Maturity promotions** that occurred (these validate artifact quality)

If no harvest reports found, exit with:
```
No harvest reports found. Run /harvest first, then re-run this module.
```

### Step 2: Match Harvested Patterns Against Generator Templates

For each harvested artifact, determine which toolkit generator template or default it relates to:

| Artifact Category | Generator Template Mapping |
|-------------------|---------------------------|
| Skills | `references/templates/feature-lifecycle.md`, skill copy protocol |
| Commands | `references/templates/start-command.md`, `automation-commands.md` |
| Hooks | `settings.json` generation, hook templates |
| Rules | `security.md`, `coding-style.md`, `git-workflow.md` generation |
| Templates | `references/templates/` directory, scaffold generation |
| Patterns | `references/enhanced-recommendations.md`, scoring system |
| Snippets | `coding-standards/` skill generation |

**Matching Algorithm:**

```
FOR each harvested_artifact IN harvest_report:
  1. IDENTIFY target_template = map_category_to_template(artifact.category)
  2. COMPARE artifact.content WITH target_template.defaults
  3. IF artifact adds new capability NOT in template:
     → CLASSIFY as "NEW_DEFAULT"
  4. IF artifact improves existing template section:
     → CLASSIFY as "TEMPLATE_UPGRADE"
  5. IF artifact reveals a missing rule or constraint:
     → CLASSIFY as "NEW_RULE"
  6. IF artifact is a pattern that should be in recommendations:
     → CLASSIFY as "RECOMMENDATION_UPDATE"
  7. RECORD match with confidence score (0-100)
```

### Step 3: Identify Improvements

For each match, generate an improvement proposal:

```markdown
## Improvement Proposal

### ID: {{IMPROVEMENT_ID}}
### Type: NEW_DEFAULT | TEMPLATE_UPGRADE | NEW_RULE | RECOMMENDATION_UPDATE
### Source Artifact: {{ARTIFACT_NAME}} ({{MATURITY_LEVEL}})
### Target Template: {{TEMPLATE_PATH}}

### Current State
[What the template currently does]

### Proposed Change
[What the template should do after applying this improvement]

### Rationale
[Why this improvement matters — based on harvest evidence]

### Impact Score: {{SCORE}}/10
### Risk Level: LOW | MEDIUM | HIGH

### Auto-Apply Eligible: YES | NO
[YES only if: Risk=LOW AND Impact>=7 AND source artifact maturity >= Beta]
```

**Improvement Types:**

| Type | Example | Typical Risk |
|------|---------|-------------|
| NEW_DEFAULT | Harvested a retry pattern used in 3+ projects → add to P0 defaults | LOW |
| TEMPLATE_UPGRADE | Harvested a better /start command structure → update template | MEDIUM |
| NEW_RULE | Harvested a "don't do X" rule → add to generated rules | LOW |
| RECOMMENDATION_UPDATE | Harvested pattern scores higher than existing recommendation → update scoring | LOW |

### Step 4: Score Improvements by Impact

Each improvement is scored on two axes:

**Impact Score (1-10):** How many future projects benefit?

| Score | Meaning |
|-------|---------|
| 1-3 | Niche — helps specific tech stacks or domains only |
| 4-6 | Moderate — helps a category of projects (e.g., all API projects) |
| 7-8 | Broad — helps most projects regardless of stack |
| 9-10 | Universal — fundamental improvement to the generation process |

**Risk Score (LOW / MEDIUM / HIGH):**

| Risk | Definition |
|------|-----------|
| LOW | Additive change, no existing behavior modified, easy to revert |
| MEDIUM | Modifies existing template, might change output for some projects |
| HIGH | Changes core generation logic, affects all future projects |

**Auto-Apply Eligibility Matrix:**

```
Auto-apply = (Risk == LOW) AND (Impact >= 7) AND (Source Maturity >= Beta)

| Risk \ Impact | 1-6 | 7-8 | 9-10 |
|---------------|-----|-----|------|
| LOW           | Report | Auto (if Beta+) | Auto (if Beta+) |
| MEDIUM        | Report | Report + Recommend | Report + Recommend |
| HIGH          | Report | Report + Warning | Report + Warning |
```

### Step 5: Generate Upgrade Recommendations or Auto-Apply

**For auto-eligible improvements (LOW risk, high impact, Beta+ source):**

1. Apply the change to the target template
2. Record the change in a changelog entry
3. Mark the source artifact as "feedback-applied" in the manifest

**For non-auto-eligible improvements:**

1. Generate a recommendation report with full context
2. Include before/after comparison
3. Include rollback instructions
4. Present to user for approval

**Maturity Promotions:**

When a harvested artifact has been used as a template improvement AND the resulting
generated toolkits work well in subsequent projects, promote the source artifact:

```
IF artifact.maturity == Alpha AND artifact.used_in_projects >= 2:
  PROMOTE to Beta
IF artifact.maturity == Beta AND artifact.used_in_projects >= 3:
  PROMOTE to Stable
```

Record promotions in the harvest feedback report.

## Output

### 1. Template Improvement Proposals

```markdown
# Harvest Feedback Report: {{PROJECT_NAME}}
Date: {{DATE}}
Source: {{HARVEST_REPORT_PATH}}

## Summary
| Metric | Value |
|--------|-------|
| Harvest reports scanned | {{N}} |
| Artifacts analyzed | {{M}} |
| Improvements identified | {{K}} |
| Auto-applied | {{A}} |
| Pending approval | {{P}} |
| Maturity promotions | {{R}} |

## Auto-Applied Upgrades

| # | Improvement | Type | Target Template | Impact | Source Artifact |
|---|-------------|------|-----------------|--------|-----------------|
| 1 | {{NAME}} | {{TYPE}} | {{TEMPLATE}} | {{SCORE}}/10 | {{ARTIFACT}} ({{MATURITY}}) |

## Pending Approval

| # | Improvement | Type | Target Template | Impact | Risk | Source Artifact |
|---|-------------|------|-----------------|--------|------|-----------------|
| 1 | {{NAME}} | {{TYPE}} | {{TEMPLATE}} | {{SCORE}}/10 | {{RISK}} | {{ARTIFACT}} ({{MATURITY}}) |

## Maturity Promotions

| Artifact | From | To | Reason |
|----------|------|----|--------|
| {{NAME}} | {{OLD_LEVEL}} | {{NEW_LEVEL}} | {{REASON}} |

## Skipped (No Match or Low Impact)

| Artifact | Reason |
|----------|--------|
| {{NAME}} | {{REASON}} |
```

### 2. Updated Templates (if auto-applied)

Modified template files with changelog entries appended:

```markdown
<!-- Harvest Feedback: {{DATE}} -->
<!-- Source: {{ARTIFACT_NAME}} from {{PROJECT_NAME}} -->
<!-- Change: {{DESCRIPTION}} -->
```

### 3. Updated Manifest

Updated `.claude/toolkit-manifest.json` with:
- `feedback_applied: true` on source artifacts
- Updated maturity levels for promoted artifacts
- `last_feedback_scan` timestamp

## Quality Gate

| Check | Threshold | Blocking? |
|-------|-----------|-----------|
| No breaking changes to existing templates | 0 breaking changes | YES |
| All auto-applied improvements scored >= 7/10 impact | Minimum 7 | YES |
| All auto-applied source artifacts >= Beta maturity | Minimum Beta | YES |
| Improvement proposals have before/after comparison | Must exist | YES |
| No duplicate improvements (already applied) | 0 duplicates | YES |
| Rollback instructions for non-trivial changes | Must exist for MEDIUM+ risk | YES |
| Maturity promotions follow promotion criteria | All criteria met | YES |

**Validation Command:**
```
FOR each auto_applied_change:
  VERIFY original_template still passes Master Validation Checklist
  VERIFY change is additive (no removed functionality)
  VERIFY change has changelog entry
```

## Dependencies

| Dependency | Purpose | Fallback |
|------------|---------|----------|
| `view() knowledge-extractor/SKILL.md` | Understand harvest report format and artifact categories | Parse reports heuristically from markdown structure |
| `view() knowledge-extractor/references/maturity-model.md` | Maturity level definitions and promotion criteria | Use inline maturity table (Alpha/Beta/Stable/Proven) |
| `view() cc-toolkit-generator-enhanced/SKILL.md` | Current template structure and generation rules | Scan `references/templates/` directory directly |

## Reusability

This module implements the **Harvest-Improve-Generate** feedback loop pattern, which is
universal for any AI-assisted development pipeline:

```
[Project Execution] → [Knowledge Extraction] → [Template Improvement] → [Better Generation]
        ↑                                                                        |
        └────────────────────────────────────────────────────────────────────────┘
```

**Reuse scenarios:**
- Any toolkit that generates from templates can use this feedback loop
- CI/CD template generators (improve pipeline templates from production incidents)
- Documentation generators (improve doc templates from user feedback)
- Code scaffolders (improve scaffolds from real-world project structures)
- AI prompt libraries (improve prompts from output quality assessments)

**To adapt for a different pipeline:**
1. Replace the "Generator Template Mapping" table with your pipeline's template structure
2. Replace the "Matching Algorithm" with your category-to-template mapping
3. Keep the scoring system, auto-apply matrix, and quality gate unchanged
4. Keep the maturity promotion logic unchanged (it references the universal maturity model)

**Key design decision:** This module never modifies templates destructively. All changes
are additive (new defaults, new rules, updated recommendations). Breaking changes require
explicit user approval and are never auto-applied.
