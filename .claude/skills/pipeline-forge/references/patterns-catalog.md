# Patterns Catalog

7 architectural patterns extracted from the PU Unicorn Replicate methodology.
Each pattern is described with: intent, structure, when to use, implementation, and examples.

---

## Pattern 1: Composable Skill Architecture

### Intent
Create self-contained, reusable AI skill modules that can be mixed, matched, and composed
into larger workflows without tight coupling.

### Structure
```
skill-name/
├── SKILL.md              # Entry point — complete skill definition
│   ├── Frontmatter       # name, description, triggers
│   ├── Architecture      # Directory layout, dependencies
│   ├── When to Use       # Trigger patterns
│   ├── Operating Modes   # AUTO/MANUAL/etc.
│   ├── Workflow           # Phase-by-phase execution
│   ├── Output Format     # Structured output templates
│   ├── Anti-Patterns     # What NOT to do
│   └── Quality Standards # Completeness checklist
├── references/           # Supporting knowledge (read-only context)
│   ├── methodology.md
│   └── criteria.md
├── templates/            # Output templates with placeholders
│   ├── output.md
│   └── report.md
├── modules/              # Sub-phases (for complex skills)
│   ├── 01-phase-one.md
│   └── 02-phase-two.md
├── examples/             # Few-shot examples
│   └── example-output.md
└── scripts/              # Executable helpers (optional)
    └── helper.sh
```

### Key Principles
1. **SKILL.md is the entry point** — always read it first
2. **Self-contained** — skill works with just its own directory
3. **Explicit interfaces** — input format, output format, triggers documented
4. **Fallback strategy** — what happens if optional dependencies are unavailable
5. **Frontmatter** — standardized metadata (name, description, triggers)

### When to Use
- You have a capability that needs to be reusable across contexts
- The capability has clear inputs, outputs, and triggers
- Multiple workflows need the same functionality

### Implementation

**Frontmatter format:**
```yaml
---
name: skill-name
description: >
  One-paragraph description of what the skill does.
  Trigger patterns listed. Use cases described.
---
```

**Minimum viable SKILL.md sections:**
1. Name and purpose (1 sentence)
2. When to Use (trigger patterns)
3. Input format
4. Output format
5. Execution steps
6. Anti-patterns

### Examples from PU Unicorn Replicate

| Skill | Size | References | Templates | Modules |
|-------|------|-----------|-----------|---------|
| `explore` | ~220 lines | 2 | 0 | 0 |
| `problem-solver-enhanced` | ~560 lines | 0 | 0 | 0 |
| `requirements-validator` | ~125 lines | 4 | 0 | 0 |
| `reverse-engineering-unicorn` | ~200 lines | 3 | 0 | 7 |
| `cc-toolkit-generator-enhanced` | ~375 lines | 3 + 11 templates | 0 | 0 |

**Rule of thumb:** If SKILL.md exceeds 400 lines, consider splitting into modules/.

---

## Pattern 2: Multi-Phase Pipeline Orchestration

### Intent
Execute a sequence of phases in strict order, passing context between them,
with checkpoints for user control and git commits at boundaries.

### Structure
```
INPUT
  ↓
PHASE 1: [Name] ─── Skill A ──→ Artifact 1
  ⏸️ CHECKPOINT 1
  git commit: "[type]: [phase-1-message]"
  ↓
PHASE 2: [Name] ─── Skill B ──→ Artifact 2
  (receives: Artifact 1 as context)
  ⏸️ CHECKPOINT 2
  git commit: "[type]: [phase-2-message]"
  ↓
PHASE N: [Name] ─── Skill N ──→ Final Output
  ⏸️ FINAL CHECKPOINT
  git commit: "[type]: [final-message]"
```

### Key Principles
1. **Strict ordering** — phases execute sequentially (unless swarm is used within a phase)
2. **Context passing** — each phase receives output of previous phases
3. **Quality gates** — between phases, validate output before proceeding
4. **Checkpoints** — user confirms before moving to next phase
5. **Git discipline** — semantic commits at phase boundaries
6. **Resumability** — pipeline can restart from any checkpoint

### Checkpoint Format
```
═══════════════════════════════════════════════════════════════
✅ PHASE [N]: [PHASE NAME]
[Summary of what was accomplished]
⏸️ "ок" — next | [other commands]
═══════════════════════════════════════════════════════════════
```

### Context Passing Strategies

| Strategy | When | Example |
|----------|------|---------|
| **File-based** | Large context | Write to `docs/`, read in next phase |
| **Variable-based** | Small context | Pass as pre-filled context parameter |
| **Implicit** | Convention | Next phase scans known directory |

### Git Commit Convention

| Phase Type | Commit Prefix |
|-----------|---------------|
| Documentation | `docs:` |
| Validation | `docs:` |
| Code generation | `feat:` |
| Configuration | `chore:` |
| Bug fixes | `fix:` |

### When to Use
- Process has natural sequential stages
- Each stage transforms work product
- User oversight needed between stages
- Audit trail (git) is important

### Examples from PU Unicorn Replicate

**`/replicate` pipeline (5 phases):**
```
Phase 0: Product Discovery → Product Discovery Brief
Phase 1: Planning         → 11 SPARC documents
Phase 2: Validation       → Validation report + BDD scenarios
Phase 3: Toolkit          → Commands + agents + rules + skills
Phase 4: Finalize         → Scaffolds + final commit
```

**`sparc-prd-mini` internal pipeline (8 phases):**
```
Phase 0: Explore    → Product Brief
Phase 1: Research   → Research_Findings.md
Phase 2: Solve      → Solution_Strategy.md
Phase 3: Specify    → Specification.md + PRD.md
Phase 4: Pseudocode → Pseudocode.md
Phase 5: Architect  → Architecture.md
Phase 6: Refine     → Refinement.md
Phase 7: Complete   → Completion.md + CLAUDE.md
```

---

## Pattern 3: Swarm of Agents

### Intent
Parallelize independent tasks by spawning multiple specialized agents
that work simultaneously, then aggregate their results.

### Structure
```
ORCHESTRATOR
    ↓ (Task tool)
┌───────────────────────┐
│ Agent A  Agent B       │  ← Independent (no cross-deps)
│ Agent C  Agent D       │
│       Agent E          │  ← May depend on A,B output
└───────────────────────┘
    ↓
AGGREGATOR
    ↓
UNIFIED RESULT
```

### Key Principles
1. **Independence** — swarm agents must not depend on each other (or explicitly declare dependencies)
2. **Clear scope** — each agent has a defined scope and criteria
3. **Parallel execution** — use Task tool to launch agents concurrently
4. **Aggregation** — orchestrator merges results, resolves conflicts
5. **Iterative** — if aggregate fails quality gate, re-run with fixes (max N iterations)

### Swarm Design Template
```markdown
| Agent | Scope | Criteria | Independence | Output |
|-------|-------|----------|-------------|--------|
| agent-A | [what it checks] | [pass/fail criteria] | Full | [output format] |
| agent-B | [what it checks] | [pass/fail criteria] | Full | [output format] |
| agent-C | [what it checks] | [pass/fail criteria] | Reads A,B | [output format] |
```

### When to Use
- Multiple independent analyses of the same input
- Validation from different perspectives
- Research across independent topics
- Generation of independent artifacts

### Anti-Patterns
❌ Swarm agents that depend on each other's output (use pipeline instead)
❌ More than 7 agents in a single swarm (diminishing returns)
❌ No aggregation step (results just dumped without synthesis)
❌ No conflict resolution strategy

### Examples from PU Unicorn Replicate

**Phase 2 Validation Swarm (5 agents):**
```
validator-stories     → INVEST criteria on user stories
validator-acceptance  → SMART criteria on acceptance criteria
validator-architecture → Target constraints compliance
validator-pseudocode  → Story coverage, implementability
validator-coherence   → Cross-document consistency (reads all above)
```

---

## Pattern 4: Skill Composition via view()

### Intent
Enable loose coupling between skills by loading external skills at runtime
via `view()` instead of copying their content. Single source of truth.

### Structure
```
orchestrator-skill/SKILL.md
  ├── "view explore skill" → reads .claude/skills/explore/SKILL.md
  ├── "view research skill" → reads .claude/skills/goap-research-ed25519/SKILL.md
  └── "view solver skill" → reads .claude/skills/problem-solver-enhanced/SKILL.md
```

### Key Principles
1. **Single Source of Truth** — skill logic lives in ONE place
2. **Runtime loading** — read skill content when needed, not before
3. **Fallback strategy** — if skill unavailable, use simplified built-in
4. **Path mapping** — support multiple environments (claude.ai vs Claude Code)
5. **No duplication** — never copy skill content into another skill

### Path Mapping Table
```markdown
| Source Environment | Path Pattern | Mapped Path |
|-------------------|-------------|-------------|
| claude.ai | `/mnt/skills/user/[name]/` | `.claude/skills/[name]/` |
| claude.ai | `/mnt/user-data/uploads/` | `docs/` |
| claude.ai | `/output/` | `docs/` or project root |
```

### Fallback Strategy Template
```markdown
**Fallbacks (if skill unavailable):**
- `explore` unavailable → built-in 3-5 Socratic questions
- `goap-research` unavailable → direct web_search
- `problem-solver` unavailable → First Principles + SCQA only
```

### When to Use
- Multiple skills need the same capability
- Skill updates should propagate automatically
- Skills need to work in different environments
- You want to avoid code duplication

### Anti-Patterns
❌ Copying skill content into another skill's SKILL.md
❌ Hardcoding paths without mapping table
❌ No fallback when dependency is unavailable
❌ Circular dependencies between skills

---

## Pattern 5: Quality Gates

See `quality-gates.md` for detailed reference.

---

## Pattern 6: Documentation-Driven Development

### Intent
Use validated documentation as the single source of truth for all downstream
code generation, toolkit creation, and implementation decisions.

### Structure
```
IDEA → DOCUMENTATION → VALIDATION → IMPLEMENTATION
        (11 docs)     (score ≥70)   (reads docs, not memory)
```

### Key Principles
1. **Docs before code** — never implement without validated documentation
2. **Anti-hallucination** — implementation reads actual docs, not AI memory
3. **Validation gate** — docs must pass quality gate before toolkit generation
4. **Traceability** — every implementation decision traces to a document
5. **Completeness** — documentation covers all aspects (requirements, architecture, testing, deployment)

### Document Set (SPARC Methodology)

| Document | Purpose | Maps To |
|----------|---------|---------|
| PRD.md | Product requirements | Overview, features, commands |
| Solution_Strategy.md | Problem analysis | Context, architect agent |
| Specification.md | Detailed requirements | Coding standards, security rules |
| Pseudocode.md | Algorithms, data flow | Planner agent, implementation refs |
| Architecture.md | System design | Tech stack, project structure |
| Refinement.md | Edge cases, testing | Code reviewer, test strategy |
| Completion.md | Deployment, CI/CD | Deploy command, hooks |
| Research_Findings.md | Market & tech research | Domain knowledge skill |
| Final_Summary.md | Executive summary | Quick reference |

### When to Use
- Building anything beyond a simple script
- Multiple people/agents will implement from the same spec
- Quality and consistency matter
- You need an audit trail of design decisions

### Anti-Patterns
❌ Generating code from memory without reading docs
❌ Skipping validation (building toolkit from unvalidated docs)
❌ Partial documentation (only PRD, no architecture)
❌ Documentation that doesn't match implementation

---

## Pattern 7: Toolkit Generation

### Intent
Transform validated documentation into a complete set of AI development instruments
(commands, agents, rules, skills, hooks) that encode domain knowledge.

### Structure
```
VALIDATED DOCS ──→ DETECT ──→ MAP ──→ GENERATE ──→ VALIDATE
                   (scan)     (score)  (templates)  (checklist)
```

### Key Principles
1. **Detection-based** — scan docs to determine what to generate
2. **Conditional generation** — some instruments only if conditions met
3. **Priority tiers** — P0 (mandatory), P1 (recommended), P2-P3 (optional)
4. **Template-based** — use templates with placeholder substitution
5. **In-place generation** — write directly into project, no archives
6. **Master validation** — checklist to verify completeness

### Priority Tiers

| Tier | When | Examples |
|------|------|---------|
| **P0 (Mandatory)** | Always | CLAUDE.md, /start, /feature, security rule, git-workflow |
| **P1 (Recommended)** | When docs provide enough context | planner agent, /plan, /test, /deploy |
| **P1 Conditional** | When specific docs detected | DDD → /feature-ent, APIs → secrets-management |
| **P2 (Optional)** | Nice to have | tdd-guide agent, review command |
| **P3 (Infrastructure)** | External integrations | .mcp.json, Docker MCP |

### Document-to-Instrument Mapping

```
EXTRACT [Document]: [field] → [instrument] [section]
```

Example:
```
EXTRACT PRD.md:       name → title, problem → context, requirements → features
EXTRACT Architecture: structure → /start P1, packages → /start P2, stack → CLAUDE.md
EXTRACT Pseudocode:   functions → planner templates, algorithms → /start P2 refs
```

### Context Budget
Keep total generated content within limits:

| Component | Target | Max |
|-----------|--------|-----|
| CLAUDE.md | 4k tokens | 6k |
| Commands (combined) | 5k | 8k |
| Rules (combined) | 3k | 5k |
| Agents + Skills | 4k | 6k |
| **Total** | ~18k | ~30k |

### When to Use
- You have validated documentation and need development instruments
- You want to encode domain knowledge into reusable Claude Code artifacts
- You need consistency across all generated instruments

### Anti-Patterns
❌ Generating toolkit from unvalidated documentation
❌ No priority tiers (everything is "mandatory")
❌ Exceeding context budget (bloated CLAUDE.md)
❌ Hardcoded content instead of reading from docs
❌ No master validation checklist
