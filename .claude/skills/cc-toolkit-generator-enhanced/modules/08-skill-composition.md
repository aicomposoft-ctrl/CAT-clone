# Module: Skill Composition

Centralized logic for copying skills into generated projects, resolving dependencies,
rewriting view() paths, verifying skill integrity, and producing a skill manifest.
This module is used by the toolkit generator whenever skills need to be bundled into
a target project.

## Input

| Parameter | Type | Description | Required |
|-----------|------|-------------|----------|
| `required_skills` | List[string] | Skill names that the target project needs (e.g., `["explore", "sparc-prd-mini", "goap-research-ed25519"]`) | YES |
| `target_project_path` | Path | Absolute path to the target project root | YES |
| `skill_source_registry` | Path | Path to the skill source directory (default: `.claude/skills/` in template repo) | YES |
| `path_rewrite_rules` | Map | Custom path rewriting overrides (optional, uses defaults if not provided) | NO |
| `verify_integrity` | Boolean | Whether to run integrity checks on copied skills (default: `true`) | NO |

## Process

### Step 1: Build Dependency Graph

For each skill in `required_skills`, scan its `SKILL.md` for dependencies:

```
FOR each skill_name IN required_skills:
  1. READ {{skill_source_registry}}/{{skill_name}}/SKILL.md
  2. EXTRACT dependency declarations:
     - view() references to other skills
     - "Dependencies" or "External Dependencies" sections
     - Fallback declarations (optional dependencies)
  3. CLASSIFY each dependency:
     - REQUIRED: skill will not function without it
     - OPTIONAL: skill has a fallback if missing
  4. ADD to dependency graph as node with edges
```

**Dependency Detection Patterns:**

```
# Pattern 1: view() references in SKILL.md
view() knowledge-extractor/references/maturity-model.md
  → dependency on skill: knowledge-extractor

# Pattern 2: Explicit dependency table
| Skill | When Used | Purpose |
|-------|-----------|---------|
| explore | Phase 1 | Clarify scope |
  → dependency on skill: explore

# Pattern 3: Module cross-references
Read module: modules/01-agent-review.md
  → internal reference (not a cross-skill dependency)

# Pattern 4: Fallback declarations
- `explore` unavailable → built-in 3 clarification questions
  → OPTIONAL dependency on skill: explore
```

### Step 2: Resolve Transitive Dependencies

Expand the dependency graph to include all transitive dependencies:

```
FUNCTION resolve_transitive(skill_name, visited=set()):
  IF skill_name IN visited:
    RETURN  # Circular dependency detected
  visited.add(skill_name)

  FOR each dep IN dependencies_of(skill_name):
    IF dep NOT IN required_skills:
      required_skills.append(dep)
    resolve_transitive(dep, visited)

FOR each skill_name IN required_skills (copy):
  resolve_transitive(skill_name)
```

**Output: Resolved Skills List**

```markdown
## Resolved Skills

### Explicitly Required
| Skill | Requested By |
|-------|-------------|
| sparc-prd-mini | toolkit generator P0 |
| explore | toolkit generator P0 |

### Transitive Dependencies
| Skill | Required By | Dependency Type |
|-------|------------|-----------------|
| goap-research-ed25519 | sparc-prd-mini | OPTIONAL |
| problem-solver-enhanced | sparc-prd-mini | OPTIONAL |

### Total: {{N}} skills to copy
```

### Step 3: Detect Circular Dependencies

Before copying, verify no circular dependency chains exist:

```
FUNCTION detect_cycles(graph):
  FOR each node IN graph:
    IF depth_first_search(node) finds back_edge:
      REPORT circular dependency: {{node}} → ... → {{node}}
      FAIL with error

# Example cycle (would be caught):
# skill-A → skill-B → skill-C → skill-A
```

If a cycle is detected, report the full chain and halt. Circular dependencies
indicate a design problem that must be resolved before copying.

### Step 4: Copy Skill Directories

Copy each skill directory from source to target with integrity verification:

```
FOR each skill_name IN resolved_skills_list:
  source = {{skill_source_registry}}/{{skill_name}}/
  target = {{target_project_path}}/.claude/skills/{{skill_name}}/

  1. VERIFY source directory exists
  2. VERIFY SKILL.md exists in source (minimum required file)
  3. COPY entire directory tree: source → target
  4. VERIFY all files copied (compare file counts)
  5. VERIFY SKILL.md readable in target
```

**Required Files per Skill:**

| File | Required? | Purpose |
|------|-----------|---------|
| `SKILL.md` | YES | Skill definition and orchestration |
| `references/` | NO | Supporting documentation |
| `templates/` | NO | Output templates |
| `modules/` | NO | Modular sub-processes |
| `examples/` | NO | Usage examples |

**Copy Protocol:**
- Preserve directory structure exactly
- Preserve file permissions
- Do NOT modify file contents during copy (path rewriting is a separate step)
- Skip `.git`, `node_modules`, `__pycache__`, and other build artifacts

### Step 5: Rewrite view() Paths

After copying, rewrite all path references in the copied skills to match the target
project structure:

**Default Path Rewriting Rules:**

| Source Pattern | Target Pattern | Context |
|----------------|----------------|---------|
| `/mnt/skills/user/{{SKILL_NAME}}/` | `.claude/skills/{{SKILL_NAME}}/` | claude.ai skill paths to Claude Code local paths |
| `/mnt/user-data/uploads/` | `docs/` | claude.ai uploads directory to project docs |
| `/output/` | `docs/` or project root | claude.ai output directory to project output |
| `view() {{SKILL_NAME}}/` | `view() .claude/skills/{{SKILL_NAME}}/` | Relative skill references |

**Rewrite Algorithm:**

```
FOR each copied_file IN target_skill_directory:
  IF file is markdown (.md) or text:
    content = READ(copied_file)

    # Rule 1: Absolute claude.ai skill paths
    content = REPLACE_ALL(
      /\/mnt\/skills\/user\/([a-zA-Z0-9_-]+)\//g,
      '.claude/skills/$1/'
    )

    # Rule 2: Upload directory references
    content = REPLACE_ALL(
      /\/mnt\/user-data\/uploads\//g,
      'docs/'
    )

    # Rule 3: Output directory references
    content = REPLACE_ALL(
      /\/output\//g,
      'docs/'
    )

    # Rule 4: Skill name aliases (known mappings)
    content = REPLACE_ALL(
      'goap-research/',
      'goap-research-ed25519/'
    )

    # Rule 5: Custom rewrite rules (from input parameter)
    FOR each rule IN path_rewrite_rules:
      content = REPLACE_ALL(rule.pattern, rule.replacement)

    WRITE(copied_file, content)
```

**Path Rewriting Examples:**

```
# Before (claude.ai format):
Read `/mnt/skills/user/explore/SKILL.md` for clarification protocol.
Scan `/mnt/user-data/uploads/` for documents.
Write output to `/output/validation-report.md`.

# After (Claude Code local format):
Read `.claude/skills/explore/SKILL.md` for clarification protocol.
Scan `docs/` for documents.
Write output to `docs/validation-report.md`.
```

### Step 6: Generate Skill Manifest

Create a `skills.json` manifest in the target project:

```json
{
  "generated": "{{DATE}}",
  "generator": "cc-toolkit-generator-enhanced",
  "generator_version": "{{VERSION}}",
  "skill_count": {{N}},
  "skills": [
    {
      "name": "{{SKILL_NAME}}",
      "path": ".claude/skills/{{SKILL_NAME}}/",
      "source": "{{SKILL_SOURCE_REGISTRY}}",
      "copied_at": "{{DATE}}",
      "files": ["SKILL.md", "references/", "templates/"],
      "dependencies": {
        "required": ["{{DEP_1}}", "{{DEP_2}}"],
        "optional": ["{{DEP_3}}"]
      },
      "paths_rewritten": {{COUNT}},
      "integrity": "PASS"
    }
  ],
  "dependency_graph": {
    "{{SKILL_A}}": ["{{SKILL_B}}", "{{SKILL_C}}"],
    "{{SKILL_B}}": [],
    "{{SKILL_C}}": ["{{SKILL_B}}"]
  }
}
```

**Manifest location:** `{{target_project_path}}/.claude/skills/skills.json`

### Step 7: Produce Health Check Report

Run a health check to verify the composed skill set is functional:

```markdown
## Skill Health Check

Date: {{DATE}}
Target: {{TARGET_PROJECT_PATH}}

### Dependency Resolution
| Check | Status |
|-------|--------|
| All required dependencies present | PASS / FAIL |
| No circular dependencies | PASS / FAIL |
| All optional dependencies noted | PASS / FAIL |

### File Integrity
| Skill | SKILL.md | References | Templates | Modules | Status |
|-------|----------|------------|-----------|---------|--------|
| {{NAME}} | PRESENT | {{N}} files | {{M}} files | {{K}} files | PASS |

### Path Rewriting
| Skill | Rewrites Applied | Unresolved Paths | Status |
|-------|-----------------|------------------|--------|
| {{NAME}} | {{N}} | {{M}} | PASS / WARN |

### Cross-Skill References
| Source Skill | References | Target Skill | Resolvable | Status |
|-------------|------------|--------------|------------|--------|
| {{A}} | view() | {{B}} | YES / NO | PASS / FAIL |

### Overall: {{PASS / FAIL}}
```

**Unresolved Path Detection:**

After rewriting, scan all copied files for remaining `/mnt/` references
or other patterns that suggest an incomplete rewrite:

```
GREP -r '/mnt/' {{target_skill_directory}}
GREP -r 'view() [a-z]' {{target_skill_directory}}  # relative view() without .claude/
```

Any matches are warnings (not blocking, but reported).

## Output

| Artifact | Location | Description |
|----------|----------|-------------|
| Copied skill directories | `{{TARGET}}/.claude/skills/{{NAME}}/` | Complete skill trees with rewritten paths |
| Skill manifest | `{{TARGET}}/.claude/skills/skills.json` | Machine-readable dependency and integrity data |
| Health check report | Inline in generation output | Human-readable verification summary |
| Resolved dependency list | Part of manifest | Full transitive dependency tree |

## Quality Gate

| Check | Threshold | Blocking? |
|-------|-----------|-----------|
| Zero circular dependencies | 0 cycles | YES |
| All view() paths resolve to existing files | 100% resolution | YES |
| All required SKILL.md files present | 100% present | YES |
| No remaining `/mnt/` paths after rewrite | 0 remaining | YES (warning if non-zero) |
| skills.json is valid JSON | Parseable | YES |
| Every skill has at least SKILL.md | Minimum 1 file | YES |
| All required dependencies included in copy list | 100% included | YES |
| Optional dependencies documented (even if absent) | All noted | NO (warning) |
| File count matches source (no missing files) | Source count == target count | YES |

**Quick Validation Command:**

```
# Verify all skills have SKILL.md
FOR each dir IN {{TARGET}}/.claude/skills/*/
  ASSERT exists(dir/SKILL.md)

# Verify no stale paths
GREP -r '/mnt/skills/user/' {{TARGET}}/.claude/skills/ → expect 0 matches
GREP -r '/mnt/user-data/' {{TARGET}}/.claude/skills/ → expect 0 matches

# Verify manifest
JSON_VALIDATE {{TARGET}}/.claude/skills/skills.json
```

## Dependencies

This module has **no external skill dependencies**. It operates purely on the
filesystem and the skill source registry.

| Dependency | Type | Purpose |
|------------|------|---------|
| Filesystem access | System | Read source skills, write to target |
| Skill source registry | Input | Directory containing source skill definitions |
| JSON serialization | System | Generate skills.json manifest |

## Reusability

This is a **critical infrastructure module** that should be extracted and reused by
any system that copies, composes, or distributes Claude Code skills.

**Reuse scenarios:**

| Scenario | How This Module Helps |
|----------|----------------------|
| Plugin installers (install.sh) | Use Steps 1-5 for safe skill installation |
| Template repositories | Use Steps 4-6 for skill bundling during fork/clone |
| Skill marketplace / registry | Use Steps 1-3 for dependency resolution |
| CI/CD skill validation | Use Step 7 for automated skill health checks |
| Cross-project skill sharing | Use Steps 4-5 for portable skill transfer |

**Extraction as standalone utility:**

This module can be extracted into a standalone skill or CLI tool:

```
skill-composer/
├── SKILL.md            # This module's logic as a skill
├── references/
│   └── path-rules.md   # Default path rewriting rules
└── templates/
    └── skills.json     # Manifest template
```

**Key design decisions:**
- Path rewriting is rule-based (regex), not heuristic, ensuring deterministic behavior
- Integrity verification happens AFTER copy, not during, for simplicity
- The manifest is JSON (machine-readable) for downstream tooling integration
- Health check is a separate step so it can be run independently of copying
- Circular dependency detection happens BEFORE copying to fail fast
