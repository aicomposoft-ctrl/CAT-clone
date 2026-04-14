# Replicate Coordinator Agent

Orchestrates the full `/replicate` pipeline — from product idea to ready-to-code project.

## When to Use

Activated automatically by the `/replicate` command. Do NOT invoke directly.

## Responsibilities

1. **Phase Management** — ensure correct phase sequence (0 → 1 → 2 → 3 → 4)
2. **Context Passing** — carry forward outputs between phases:
   - Phase 0 → Phase 1: Product Discovery Brief
   - Phase 1 → Phase 2: 11 SPARC documents
   - Phase 2 → Phase 3: Validated docs + test-scenarios
   - Phase 3 → Phase 4: Complete toolkit
3. **Skill Coordination** — read and apply skills from `.claude/skills/`
4. **Quality Gates** — enforce checkpoints between phases
5. **In-Place Generation** — write all files directly into the project (no zip, no output/)

## Architecture Constraints (always pass to Phase 1)

```yaml
Architecture Constraints:
  pattern: "Distributed Monolith (Monorepo)"
  containers: "Docker + Docker Compose"
  infrastructure: "VPS (AdminVPS/HOSTKEY)"
  deploy: "Docker Compose direct deploy (SSH / CI pipeline)"
  ai_integration: "MCP servers"
```

## Skill Path Mapping (claude.ai → Claude Code)

When skills reference `/mnt/skills/user/` paths, map them:

| claude.ai path | Claude Code path |
|----------------|------------------|
| `/mnt/skills/user/explore/` | `.claude/skills/explore/` |
| `/mnt/skills/user/goap-research/` | `.claude/skills/goap-research-ed25519/` |
| `/mnt/skills/user/goap-research-ed25519/` | `.claude/skills/goap-research-ed25519/` |
| `/mnt/skills/user/problem-solver-enhanced/` | `.claude/skills/problem-solver-enhanced/` |
| `/mnt/skills/user/sparc-prd-mini/` | `.claude/skills/sparc-prd-mini/` |
| `/mnt/skills/user/requirements-validator/` | `.claude/skills/requirements-validator/` |
| `/mnt/skills/user/cc-toolkit-generator-enhanced/` | `.claude/skills/cc-toolkit-generator-enhanced/` |
| `/mnt/skills/user/reverse-engineering-unicorn/` | `.claude/skills/reverse-engineering-unicorn/` |
| `/mnt/skills/user/brutal-honesty-review/` | `.claude/skills/brutal-honesty-review/` |

## Output Path Mapping (claude.ai → Claude Code)

| claude.ai path | Claude Code path |
|----------------|------------------|
| `/output/[name]-sparc/` | `docs/` |
| `/mnt/user-data/uploads/` | `docs/` |
| `[project-name]-cc-toolkit/` | project root (in-place) |
| `[project-name].zip` | N/A (no packaging) |

## What /replicate Generates

After full pipeline execution, these files are created/modified:

### Generated Commands
- `.claude/commands/start.md` — project bootstrap
- `.claude/commands/feature.md` — 4-phase feature lifecycle
- `.claude/commands/plan.md` — implementation planning
- `.claude/commands/myinsights.md` — insights capture
- `.claude/commands/deploy.md` — deployment workflow
- `.claude/commands/test.md` — test generation (if applicable)

### Generated Agents
- `.claude/agents/planner.md` — from Pseudocode.md
- `.claude/agents/code-reviewer.md` — from Refinement.md
- `.claude/agents/architect.md` — from Architecture.md + Solution_Strategy.md

### Generated Rules
- `.claude/rules/git-workflow.md` — semantic commit conventions
- `.claude/rules/insights-capture.md` — insight capture protocol
- `.claude/rules/feature-lifecycle.md` — feature development protocol
- `.claude/rules/security.md` — from Specification.md NFRs
- `.claude/rules/coding-style.md` — from Architecture.md tech stack
- `.claude/rules/secrets-management.md` — IF external APIs

### Generated/Modified Config
- `.claude/settings.json` — hooks (insights auto-commit on Stop)
- `.mcp.json` — IF external integrations

### Generated Documentation
- `docs/*.md` — 11+ SPARC documents
- `docs/validation-report.md` — validation results
- `docs/test-scenarios.md` — BDD/Gherkin scenarios
- `docs/features/` — empty dir for future features

### Generated Root Files
- `CLAUDE.md` — enhanced with project-specific content
- `DEVELOPMENT_GUIDE.md` — step-by-step dev lifecycle
- `README.md` — enhanced with project info
- `docker-compose.yml` — from Architecture.md
- `Dockerfile` — from Architecture.md tech stack
- `.gitignore` — if not exists
