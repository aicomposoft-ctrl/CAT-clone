# Extended Mapping Matrix

Complete mapping from idea2prd-manual documents to Claude Code instruments.

## Document Detection

### idea2prd-manual Output Structure

```
project-root/
├── docs/
│   ├── prd/PRD.md
│   ├── ddd/
│   │   ├── strategic/
│   │   │   ├── bounded-contexts.md
│   │   │   └── context-map.md
│   │   └── tactical/
│   │       ├── aggregates/
│   │       ├── entities/
│   │       ├── value-objects/
│   │       ├── events/
│   │       └── repositories/
│   ├── adr/
│   │   ├── ADR-001-*.md
│   │   ├── ADR-002-*.md
│   │   └── ... (10+)
│   ├── c4/
│   │   ├── context.mermaid
│   │   ├── container.mermaid
│   │   └── component.mermaid
│   ├── pseudocode/
│   │   ├── {Aggregate}.pseudo
│   │   └── {Service}.pseudo
│   ├── tests/
│   │   └── {feature}.feature (Gherkin)
│   ├── fitness/
│   │   └── fitness-functions.md
│   ├── completion/
│   │   └── COMPLETION_CHECKLIST.md
│   └── INDEX.md
├── .ai-context/
│   ├── README.md
│   ├── architecture-summary.md
│   ├── key-decisions.md
│   ├── domain-glossary.md
│   ├── bounded-contexts.md
│   ├── coding-standards.md
│   ├── fitness-rules.md
│   └── pseudocode-index.md
└── README.md
```

---

## Complete Document → Instrument Mapping

### PRD Documents

| Document | Section | Primary Output | Secondary Output |
|----------|---------|----------------|------------------|
| PRD.md | Overview | CLAUDE.md overview | - |
| PRD.md | Functional Requirements | /plan command | feature-x/ skills |
| PRD.md | Non-Functional Requirements | security.md, performance.md | hooks |
| PRD.md | User Stories | commands | testing-patterns/ skill |
| PRD.md | User Journeys | workflow skills | - |
| PRD.md | Constraints | rules | CLAUDE.md Critical Rules |

### DDD Strategic Documents

| Document | Section | Primary Output | Secondary Output |
|----------|---------|----------------|------------------|
| bounded-contexts.md | Context definitions | domain-expert.md agent | CLAUDE.md Domain Model |
| bounded-contexts.md | Context responsibilities | Agent scope definitions | Skill boundaries |
| bounded-contexts.md | Ubiquitous Language | domain-glossary rule | project-context/ skill |
| context-map.md | Relationships | Integration hooks | architect.md knowledge |
| context-map.md | Shared Kernel | Shared skills | coding-standards/ |
| context-map.md | Anti-Corruption Layer | Validation hooks | security.md |

### DDD Tactical Documents

| Document | Section | Primary Output | Secondary Output |
|----------|---------|----------------|------------------|
| aggregates/*.md | Aggregate Root | ddd-validator.md agent | aggregate-patterns/ skill |
| aggregates/*.md | Invariants | PreToolUse validation hooks | domain-model.md rule |
| aggregates/*.md | Business Rules | coding-style.md rules | validation hooks |
| entities/*.md | Entity definitions | Type checking hooks | coding-standards/ skill |
| entities/*.md | Identity rules | validation patterns | - |
| value-objects/*.md | VO definitions | Immutability rules | coding-standards/ skill |
| events/*.md | Domain Events | event-handlers/ skill | PostToolUse hooks |
| events/*.md | Event handlers | Event-driven hooks | workflow skills |
| repositories/*.md | Repository patterns | MCP integration hints | api-patterns/ skill |

### ADR Documents

| Document | Decision Type | Primary Output | Secondary Output |
|----------|---------------|----------------|------------------|
| ADR-*-technology.md | Tech stack | CLAUDE.md Tech Stack | coding-standards/ skill |
| ADR-*-architecture.md | Architecture | architect.md agent | CLAUDE.md diagrams |
| ADR-*-pattern.md | Design pattern | coding-style.md | pattern skills |
| ADR-*-security.md | Security | security.md rule | security hooks |
| ADR-*-integration.md | External system | .mcp.json | integration skills |
| ADR-*-data.md | Data decisions | database rules | validation hooks |
| ADR-*-testing.md | Test strategy | testing.md rule | testing-patterns/ skill |
| Any ADR | Rejected alternatives | Anti-pattern rules | code-reviewer knowledge |

### C4 Diagrams

| Document | Level | Primary Output | Secondary Output |
|----------|-------|----------------|------------------|
| context.mermaid | System Context | CLAUDE.md overview | architect.md context |
| container.mermaid | Container | CLAUDE.md structure | Agent boundaries |
| component.mermaid | Component | Skill boundaries | coding-standards/ |

### Pseudocode Documents

| Document | Element | Primary Output | Secondary Output |
|----------|---------|----------------|------------------|
| {Aggregate}.pseudo | FUNCTION | planner.md templates | coding-standards/ |
| {Aggregate}.pseudo | VALIDATE | PreToolUse hooks | validation rules |
| {Aggregate}.pseudo | FOR/IF logic | Algorithm patterns | tdd-guide knowledge |
| {Aggregate}.pseudo | EMIT events | event-handlers/ skill | PostToolUse hooks |
| {Aggregate}.pseudo | Error handling | error patterns | code-reviewer knowledge |
| {Service}.pseudo | Service methods | /command templates | workflow skills |

### Gherkin Test Documents

| Document | Element | Primary Output | Secondary Output |
|----------|---------|----------------|------------------|
| *.feature | Feature | /test command scope | testing-patterns/ section |
| *.feature | Scenario | Test templates | validation hooks |
| *.feature | Given | Setup patterns | fixture skills |
| *.feature | When | Action templates | command triggers |
| *.feature | Then | Assertion rules | PostToolUse hooks |
| *.feature | Background | Shared fixtures | testing-patterns/ skill |
| *.feature | Scenario Outline | Parameterized tests | data-driven hooks |
| *.feature | Examples | Test data | fixture patterns |

### Fitness Functions

| Function Type | Primary Output | Secondary Output |
|---------------|----------------|------------------|
| BC Independence | /validate-ddd command | architecture rule |
| Aggregate Size | PreToolUse hook | coding rule |
| Method Length | PostToolUse hook | coding-style rule |
| Response Time | Performance hook | monitoring hook |
| Test Coverage | PostToolUse hook | testing rule |
| Security Scan | PreToolUse hook | security rule |
| Dependency Check | PreToolUse hook | security rule |
| Code Complexity | PostToolUse hook | coding rule |

### Completion Checklist

| Section | Primary Output | Secondary Output |
|---------|----------------|------------------|
| Dev Environment | CLAUDE.md commands | setup skill |
| CI/CD Pipeline | hooks configuration | /deploy command |
| Docker/K8s | deployment hooks | infra skill |
| Monitoring | alert hooks | observability skill |
| Security Checklist | security.md | security hooks |
| Pre-launch | Stop verification hook | checklist command |

### .ai-context Files

| File | Integration Target | Priority |
|------|-------------------|----------|
| README.md | CLAUDE.md Overview | P0 |
| architecture-summary.md | CLAUDE.md Architecture | P0 |
| key-decisions.md | CLAUDE.md Decisions | P0 |
| domain-glossary.md | project-context/ skill | P1 |
| bounded-contexts.md | domain-model.md rule | P0 |
| coding-standards.md | coding-style.md rule | P0 |
| fitness-rules.md | fitness-functions.md rule | P1 |
| pseudocode-index.md | planner.md agent | P1 |

---

## Extraction Patterns

### From DDD Strategic

```
EXTRACT bounded-contexts.md:
  - Context names → Agent naming
  - Context responsibilities → Agent description triggers
  - Ubiquitous language → domain-glossary rule + skill
  - Context boundaries → Skill scope definitions
  
EXTRACT context-map.md:
  - Upstream/Downstream → Integration priority
  - Shared Kernel → Shared coding-standards
  - Anti-Corruption Layer → Validation hooks
  - Published Language → API skills
```

### From DDD Tactical

```
EXTRACT aggregates/*.md:
  - Aggregate name → {Aggregate}Validator in ddd-validator agent
  - Invariants → PreToolUse validation hooks
  - Commands → /command templates
  - Factory methods → Creation patterns in skill
  
EXTRACT events/*.md:
  - Event name → Hook trigger
  - Event data → Validation schema
  - Handlers → event-handlers/ skill sections
  - Subscribers → PostToolUse hook chains
```

### From ADRs

```
FOR EACH adr/*.md:
  EXTRACT:
    - Title → Rule/skill name candidate
    - Status → (if Accepted) include, (if Deprecated) exclude
    - Context → Background for CLAUDE.md
    - Decision → Rule content
    - Consequences → Trade-off documentation
    - Rejected alternatives → Anti-pattern rules
    
  CLASSIFY by keywords:
    - "security", "auth", "encryption" → security.md
    - "performance", "scale", "cache" → performance rules
    - "test", "coverage", "TDD" → testing.md
    - "API", "REST", "GraphQL" → api-patterns/ skill
    - "database", "storage", "persistence" → data rules
    - technology names → coding-standards/
```

### From Pseudocode

```
FOR EACH pseudocode/*.pseudo:
  PARSE structure:
    - FUNCTION signature → Method template for planner
    - VALIDATE statements → Hook conditions
    - FOR/WHILE loops → Algorithm pattern
    - IF conditions → Branching logic
    - EMIT statements → Event hooks
    - RETURN type → Validation schema
    
  GENERATE:
    - Algorithm templates for planner.md
    - Validation hooks for complex functions
    - Test case hints for tdd-guide.md
```

### From Gherkin

```
FOR EACH tests/*.feature:
  PARSE:
    - Feature name → /test command scope
    - @tags → Test categorization
    - Scenario name → Test template
    - Given steps → Setup skill
    - When steps → Action command
    - Then steps → Assertion hook
    - Examples table → Data patterns
    
  GENERATE:
    - /test command with feature awareness
    - testing-patterns/ skill sections
    - Validation hooks from Then steps
```

### From Fitness Functions

```
FOR EACH fitness function:
  CLASSIFY:
    - Architecture fitness → ddd-validator agent
    - Code quality fitness → PostToolUse hook
    - Security fitness → PreToolUse hook
    - Performance fitness → monitoring hook
    
  GENERATE:
    - Hook with threshold check
    - Rule with rationale
    - /validate-ddd command section
```

---

## Priority Scoring (Enhanced)

### Base Scores by Document Type

| Document Type | Base Score | Max Boost |
|---------------|------------|-----------|
| .ai-context/* | +15 | +5 |
| PRD.md | +10 | +5 |
| DDD Strategic | +12 | +8 |
| DDD Tactical | +10 | +10 |
| ADR (>10) | +10 | +5 |
| Pseudocode | +10 | +5 |
| Gherkin | +10 | +5 |
| Fitness | +8 | +5 |
| C4 | +5 | +3 |
| Completion | +5 | +3 |

### Boost Conditions

```
# DDD Boosts
IF aggregates/ has >5 files: +5 to ddd-validator
IF events/ has >3 files: +5 to event-handlers skill
IF bounded-contexts >3: +5 to domain-expert agent

# ADR Boosts  
IF adr/ has >15 files: +5 to architect agent
IF adr/ has security ADR: +5 to security rules
IF adr/ has testing ADR: +3 to testing rules

# Pseudocode Boosts
IF pseudocode/ has >5 files: +5 to planner agent
IF pseudocode contains STATE MACHINE: +5 to workflow skill

# Gherkin Boosts
IF tests/ has >10 scenarios: +5 to testing-patterns
IF tests/ has @security tag: +3 to security hooks

# Fitness Boosts
IF fitness has >5 functions: +5 to validation hooks
IF fitness has architecture rules: +5 to ddd-validator
```

---

## Context Budget Allocation (Enhanced)

| Category | Documents | Budget | Strategy |
|----------|-----------|--------|----------|
| CLAUDE.md Core | .ai-context, PRD, C4 | 4-6k | Direct integration |
| Domain Knowledge | DDD Strategic | 1.5-2k | skill references |
| Code Patterns | DDD Tactical, Pseudocode | 1.5-2k | skill + hook |
| Quality | Fitness, Gherkin | 1-1.5k | rules + hooks |
| Architecture | ADR, C4 | 1-1.5k | agent + CLAUDE.md |
| Deployment | Completion | 0.5-1k | command + hooks |
| **Total** | All | 10-14k | <7% of 200k |

---

## MCP Matching (Enhanced)

### From ADR Integration Decisions

```
SCAN adr/*.md for:
  - "GitHub" → @modelcontextprotocol/server-github
  - "PostgreSQL", "Postgres" → @modelcontextprotocol/server-postgres
  - "MongoDB" → @modelcontextprotocol/server-mongodb
  - "Redis" → @modelcontextprotocol/server-redis
  - "Supabase" → @supabase/mcp-server
  - "AWS", "S3", "Lambda" → @aws/mcp-server
  - "Stripe" → @stripe/mcp-server
  - "Slack" → @modelcontextprotocol/server-slack
  - "Notion" → @modelcontextprotocol/server-notion
```

### From DDD Repository Patterns

```
SCAN repositories/*.md for:
  - Database type → Matching MCP server
  - External API mentions → API-specific MCP
  - Message queue → Queue MCP if available
```
