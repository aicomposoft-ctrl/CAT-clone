# Enhanced CLAUDE.md Template

Template for generating CLAUDE.md with full .ai-context/ integration.

---

## Template Structure

```markdown
# Project: {{PROJECT_NAME}}

## Overview

{{FROM_AI_CONTEXT_README_OR_PRD}}

**Domain:** {{DOMAIN_DESCRIPTION}}
**Key Users:** {{USER_PERSONAS}}

## Architecture

{{FROM_AI_CONTEXT_ARCHITECTURE_SUMMARY}}

### System Context (C4 Level 1)

{{C4_CONTEXT_SUMMARY}}

### Containers (C4 Level 2)

{{C4_CONTAINERS_SUMMARY}}

## Key Decisions

{{FROM_AI_CONTEXT_KEY_DECISIONS}}

| ADR | Decision | Rationale |
|-----|----------|-----------|
{{TOP_5_ADRS}}

## Domain Model

### Bounded Contexts

{{FROM_AI_CONTEXT_BOUNDED_CONTEXTS}}

| Context | Responsibility | Key Aggregates |
|---------|---------------|----------------|
{{CONTEXT_TABLE}}

### Ubiquitous Language

{{KEY_TERMS_FROM_GLOSSARY}}

## Tech Stack

{{FROM_ARCHITECTURE_OR_ADRS}}

- **Frontend:** {{FRONTEND}}
- **Backend:** {{BACKEND}}
- **Database:** {{DATABASE}}
- **Infrastructure:** {{INFRA}}
- **Key Libraries:** {{LIBRARIES}}

## Project Structure

```
{{DIRECTORY_STRUCTURE}}
```

## Development Commands

```bash
# Install dependencies
{{INSTALL_CMD}}

# Start development
{{DEV_CMD}}

# Run tests
{{TEST_CMD}}

# Validate DDD
{{VALIDATE_CMD}}

# Build
{{BUILD_CMD}}
```

## Coding Standards

{{FROM_AI_CONTEXT_CODING_STANDARDS}}

### DDD Conventions

- Aggregates in `src/domain/{context}/aggregates/`
- Events in `src/domain/{context}/events/`
- Use past tense for events (OrderPlaced)
- Keep aggregates ≤{{MAX_ENTITIES}} entities

## Quality Gates

{{FROM_AI_CONTEXT_FITNESS_RULES}}

| Fitness Function | Target |
|------------------|--------|
{{FITNESS_TABLE}}

## Critical Rules

- **IMPORTANT:** {{CRITICAL_RULE_1}}
- **NEVER:** {{CRITICAL_RULE_2}}
- **ALWAYS:** {{CRITICAL_RULE_3}}

## Available Agents

| Agent | Purpose | Trigger |
|-------|---------|---------|
| planner | Feature planning | "plan", "break down" |
| code-reviewer | Quality review | "review", "check" |
| architect | System design | "design", "ADR" |
| domain-expert | Domain knowledge | "domain", "context" |
| ddd-validator | DDD validation | "validate", "DDD" |
| tdd-guide | Test-first development | "test", "TDD" |

## Available Skills

- **project-context/** — Full domain knowledge
- **coding-standards/** — Code conventions with DDD
- **testing-patterns/** — Gherkin-based testing
- **aggregate-patterns/** — DDD tactical patterns
- **event-handlers/** — Domain event patterns

## Quick Commands

| Command | Purpose |
|---------|---------|
| `/plan [feature]` | Plan implementation |
| `/test [scope]` | Run/generate tests |
| `/validate-ddd` | Validate DDD compliance |
| `/deploy [env]` | Deploy to environment |
| `/context [name]` | Navigate bounded contexts |

## External Integrations

{{IF_MCP_CONFIGURED}}
| Service | MCP Server | Config |
|---------|------------|--------|
{{MCP_TABLE}}
{{/IF_MCP_CONFIGURED}}

## Testing Strategy

{{FROM_GHERKIN_SUMMARY}}

**Coverage Targets:**
- Lines: {{LINE_COVERAGE}}%
- Branches: {{BRANCH_COVERAGE}}%
- Critical Paths: 100%

## Deployment

{{FROM_COMPLETION_SUMMARY}}
```

---

## Fill Instructions

### Priority 1: .ai-context/ Integration

If `.ai-context/` exists, use as primary source:

| .ai-context File | Target Section |
|------------------|----------------|
| README.md | Overview |
| architecture-summary.md | Architecture |
| key-decisions.md | Key Decisions |
| bounded-contexts.md | Domain Model |
| domain-glossary.md | Ubiquitous Language |
| coding-standards.md | Coding Standards |
| fitness-rules.md | Quality Gates |
| pseudocode-index.md | Reference for agents |

### Priority 2: docs/ Fallback

If specific .ai-context file missing, extract from:

| Section | Primary Source | Secondary Source |
|---------|----------------|------------------|
| Overview | docs/prd/PRD.md | Research_Findings.md |
| Architecture | docs/c4/*.mermaid | Architecture.md |
| Key Decisions | docs/adr/*.md | Solution_Strategy.md |
| Domain Model | docs/ddd/strategic/ | Specification.md |
| Tech Stack | docs/adr/*-technology.md | Architecture.md |
| Testing | docs/tests/*.feature | Refinement.md |
| Deployment | docs/completion/ | Completion.md |

### Priority 3: SPARC Fallback

If idea2prd-manual docs not present, use SPARC mapping from original skill.

---

## Size Guidelines

| Section | Target Lines | Max Lines |
|---------|--------------|-----------|
| Overview | 5-10 | 15 |
| Architecture | 15-25 | 40 |
| Key Decisions | 10-15 | 25 |
| Domain Model | 15-25 | 40 |
| Tech Stack | 10-15 | 20 |
| Project Structure | 15-20 | 30 |
| Commands | 10-15 | 20 |
| Coding Standards | 15-20 | 30 |
| Quality Gates | 5-10 | 15 |
| Agents/Skills/Commands | 15-20 | 30 |
| **Total** | ~150-200 | ~300 |

**Target:** ~4k tokens (with .ai-context)
**Max:** 6k tokens

---

## Anti-Patterns

❌ **DON'T:** Duplicate .ai-context content verbatim (reference instead)
❌ **DON'T:** Include all ADRs (select top 5-7)
❌ **DON'T:** List all glossary terms (select key 10-15)
❌ **DON'T:** Include full C4 diagrams (summarize)
❌ **DON'T:** Copy entire fitness functions (reference skill)

✅ **DO:** Summarize and reference
✅ **DO:** Link to skills for details
✅ **DO:** Keep actionable commands prominent
✅ **DO:** Focus on daily-use information
