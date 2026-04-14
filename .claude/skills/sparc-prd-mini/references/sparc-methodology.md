# SPARC Methodology Reference

Complete guide to SPARC (Specification, Pseudocode, Architecture, Refinement, Completion) methodology for AI-assisted software development and Vibe Coding.

## Overview

SPARC — структурированная методология разработки ПО, оптимизированная для работы с AI coding assistants (Claude Code, Cursor, Aider, GitHub Copilot). Каждая фаза создаёт артефакты, которые AI может использовать для генерации качественного кода.

## Philosophy

### Why SPARC for Vibe Coding?

1. **AI-Readable Structure:** Документы структурированы для оптимального понимания LLM
2. **Incrementally Refinable:** Каждая фаза уточняет предыдущую
3. **Verification Points:** Checkpoints предотвращают cascade errors
4. **Context-Rich:** Достаточно контекста для осмысленной кодогенерации

### Traditional vs SPARC Development

```
Traditional:
Requirements → Design → Code → Test → Deploy
    ↑                                    │
    └────────── Feedback Loop ───────────┘
    (Long cycles, expensive corrections)

SPARC:
Spec ⟷ Pseudo ⟷ Arch ⟷ Refine ⟷ Complete
  ↓       ↓        ↓        ↓         ↓
 [AI verifies each transition before proceeding]
    (Short cycles, early correction)
```

## Phase Details

### 1. Specification (SPEC)

**Purpose:** Define WHAT needs to be built with precision.

**Key Outputs:**
- Functional Requirements (User Stories)
- Non-Functional Requirements (NFRs)
- Acceptance Criteria
- Constraints & Assumptions

**AI Optimization Tips:**
```markdown
✅ GOOD for AI:
"User can login with email/password. On success, redirect to /dashboard.
On failure, show inline error and allow retry. Lock account after 5 failures."

❌ BAD for AI:
"User should be able to login."
```

**Specification Completeness Checklist:**
- [ ] Every feature has clear acceptance criteria
- [ ] Edge cases explicitly mentioned
- [ ] Error states defined
- [ ] Success metrics quantified

### 2. Pseudocode (PSEUDO)

**Purpose:** Define HOW logic should work without language syntax.

**Key Outputs:**
- Algorithm descriptions
- Data structures
- State transitions
- API contracts

**Best Practices for AI-Readable Pseudocode:**

```
✅ GOOD:
FUNCTION validateEmail(email):
    INPUT: email (string)
    OUTPUT: boolean
    
    1. IF email is empty THEN RETURN false
    2. IF email does not match regex /^[^@]+@[^@]+\.[^@]+$/ THEN RETURN false
    3. IF email length > 255 THEN RETURN false
    4. RETURN true

❌ BAD:
validate email - check if it's correct
```

**Pseudocode Detail Levels:**

| Level | Use Case | Detail |
|-------|----------|--------|
| High | Architecture discussions | Function names, inputs/outputs |
| Medium | Implementation planning | Control flow, key logic |
| Detailed | Complex algorithms | Every condition, edge case |

### 3. Architecture (ARCH)

**Purpose:** Define system STRUCTURE and technology choices.

**Key Outputs:**
- Component diagrams
- Technology stack
- Data models
- Integration points
- Security architecture

**AI-Friendly Architecture Patterns:**

```markdown
✅ GOOD:
## Authentication Flow
```
[Client] → POST /auth/login → [API Gateway]
                                    ↓
                            [Auth Service]
                                    ↓
                            [User DB] ← validate credentials
                                    ↓
                            [Token Service] ← generate JWT
                                    ↓
                            Response: {token, refreshToken}
```

❌ BAD:
"Use standard OAuth flow"
```

**Architecture Decision Records (ADR) Template:**

```markdown
## ADR-001: Database Selection

**Status:** Accepted
**Context:** Need persistent storage for user data with ACID compliance
**Decision:** PostgreSQL 16
**Rationale:** 
- JSON support for flexible schemas
- Strong ecosystem (Prisma, TypeORM support)
- Team familiarity
**Consequences:**
- Need to manage connection pooling
- Requires managed service or self-hosting
```

### 4. Refinement (REFINE)

**Purpose:** Improve quality, handle edge cases, optimize.

**Key Outputs:**
- Test specifications
- Performance optimizations
- Security hardening
- Error handling matrix

**Test Specification Format:**

```markdown
## Test Suite: UserAuthentication

### Unit Tests
| Test ID | Description | Input | Expected Output |
|---------|-------------|-------|-----------------|
| UT-001 | Valid login | valid email, password | {success: true, token} |
| UT-002 | Invalid password | valid email, wrong password | {success: false, error: "AUTH_FAILED"} |
| UT-003 | Locked account | valid credentials, locked account | {success: false, error: "ACCOUNT_LOCKED"} |

### Integration Tests
| Test ID | Scenario | Steps | Expected Result |
|---------|----------|-------|-----------------|
| IT-001 | Login flow | 1. POST /login with valid creds | 200, JWT in response |
| IT-002 | Rate limiting | 1. POST /login 11 times in 1 min | 429 on 11th request |
```

**Error Handling Matrix:**

| Error Code | HTTP | Trigger | User Message | System Action |
|------------|------|---------|--------------|---------------|
| AUTH_001 | 401 | Invalid credentials | "Email or password incorrect" | Log attempt |
| AUTH_002 | 423 | Account locked | "Account locked. Contact support." | Alert security |
| AUTH_003 | 429 | Rate limit exceeded | "Too many attempts. Wait 15 minutes." | Temp block IP |

### 5. Completion (COMP)

**Purpose:** Ensure production readiness.

**Key Outputs:**
- Deployment procedures
- CI/CD configuration
- Monitoring setup
- Documentation
- Handoff checklists

**Deployment Readiness Checklist:**

```markdown
## Pre-Deployment
- [ ] All tests passing (unit, integration, e2e)
- [ ] Security scan clear (no critical/high vulnerabilities)
- [ ] Performance benchmarks met
- [ ] Database migrations tested
- [ ] Rollback procedure documented and tested
- [ ] Feature flags configured
- [ ] Monitoring dashboards ready
- [ ] Alerting rules configured
- [ ] Documentation updated

## Deployment
- [ ] Maintenance window announced
- [ ] Backup created
- [ ] Deploy to staging
- [ ] Smoke tests on staging
- [ ] Deploy to production
- [ ] Smoke tests on production
- [ ] Monitor metrics for 30 minutes

## Post-Deployment
- [ ] Verify all health checks green
- [ ] Check error rates
- [ ] Confirm logs flowing
- [ ] Update status page
```

## SPARC for Different Project Types

### API Development

```
Spec:    OpenAPI/Swagger spec, endpoint definitions
Pseudo:  Request/response flows, validation logic
Arch:    Service architecture, auth flow, rate limiting
Refine:  API tests, error codes, pagination
Complete: API docs, SDK generation, versioning strategy
```

### Frontend Application

```
Spec:    User stories, wireframes, interaction specs
Pseudo:  State management logic, form validation
Arch:    Component hierarchy, routing, state architecture
Refine:  Unit tests, accessibility, performance optimization
Complete: Build pipeline, CDN config, monitoring
```

### Data Pipeline

```
Spec:    Data sources, transformations, SLAs
Pseudo:  ETL logic, validation rules
Arch:    Pipeline architecture, storage strategy
Refine:  Data quality tests, error recovery
Complete: Orchestration, monitoring, alerting
```

## Integration with AI Tools

### Claude Code

```bash
# Start project with SPARC context
claude --project ./my-sparc-project

# Claude will use CLAUDE.md and SPARC docs as context
```

**Recommended CLAUDE.md:**

```markdown
# Project: [Name]

## Documentation
Read these SPARC documents before implementing:
1. Specification.md - Requirements and acceptance criteria
2. Pseudocode.md - Implementation logic
3. Architecture.md - System design decisions
4. Refinement.md - Testing and edge cases
5. Completion.md - Deployment requirements

## Coding Standards
- Follow patterns in existing code
- Add tests for new functionality
- Update docs when changing interfaces
```

### Cursor

```markdown
# .cursorrules

## Project Context
This project follows SPARC methodology. Reference documents:
- /docs/Specification.md for requirements
- /docs/Architecture.md for system design
- /docs/Refinement.md for testing requirements

## Implementation Rules
1. Match pseudocode in Pseudocode.md when implementing algorithms
2. Follow error codes defined in Refinement.md
3. Ensure tests cover acceptance criteria from Specification.md
```

### Aider

```bash
# Add SPARC docs as read-only context
aider --read Specification.md Architecture.md Pseudocode.md

# Or use architect mode for design discussions
aider --architect --read Architecture.md
```

## Quality Metrics

### Document Quality Score

| Metric | Weight | Criteria |
|--------|--------|----------|
| Completeness | 30% | All sections filled |
| Consistency | 25% | No contradictions across docs |
| Specificity | 25% | Concrete, not vague |
| Testability | 20% | Claims verifiable |

### Vibe Coding Readiness Score

| Factor | Score | Description |
|--------|-------|-------------|
| 1 | Not ready | Missing major sections |
| 2 | Partial | Has structure, lacks detail |
| 3 | Ready | Can generate code with supervision |
| 4 | Excellent | Can generate production code |
| 5 | Optimal | AI can work autonomously |

## Common Pitfalls

### Spec Phase
❌ Vague requirements ("system should be fast")
✅ Quantified requirements ("API response < 200ms p99")

### Pseudo Phase
❌ Implementation-specific ("use Redis ZADD")
✅ Logic-focused ("add to sorted set with score")

### Arch Phase
❌ Over-engineering ("microservices for MVP")
✅ Right-sized ("monolith with clear module boundaries")

### Refine Phase
❌ Happy path only
✅ Explicit error cases and edge conditions

### Complete Phase
❌ "Deploy to production"
✅ Step-by-step runbook with rollback

## References

- [SPARC Framework Repository](https://github.com/ruvnet/sparc)
- [Claude Flow SPARC Integration](https://github.com/ruvnet/claude-flow)
- [SPARC CLI Documentation](https://github.com/ruvnet/sparc/tree/main/sparc_cli)
