# DDD-Specific Skill Templates

Enhanced skill templates for DDD-aware Claude Code instruments.

---

## aggregate-patterns/ Skill

**Source:** DDD Tactical (aggregates, entities, value-objects)

```markdown
---
name: aggregate-patterns
description: DDD aggregate and entity patterns for {{PROJECT_NAME}}. Use when implementing aggregates, entities, value objects, or domain logic. Keywords: aggregate, entity, value object, invariant, domain, DDD.
---

# Aggregate Patterns

## Project Aggregates

{{AGGREGATE_LIST_WITH_DESCRIPTIONS}}

## Aggregate Template

```{{LANGUAGE}}
{{AGGREGATE_TEMPLATE_FOR_STACK}}
```

## Invariant Patterns

### Validation Pattern

```{{LANGUAGE}}
{{VALIDATION_PATTERN}}
```

### Factory Pattern

```{{LANGUAGE}}
{{FACTORY_PATTERN}}
```

## Entity Patterns

### Identity Pattern

```{{LANGUAGE}}
{{ENTITY_ID_PATTERN}}
```

## Value Object Patterns

### Immutable VO

```{{LANGUAGE}}
{{VALUE_OBJECT_PATTERN}}
```

## Common Invariants

| Aggregate | Invariant | Validation |
|-----------|-----------|------------|
{{INVARIANTS_TABLE}}
```

---

## event-handlers/ Skill

**Source:** DDD Tactical (events)

```markdown
---
name: event-handlers
description: Domain event handling patterns for {{PROJECT_NAME}}. Use when implementing event emission, handlers, or event-driven workflows. Keywords: event, handler, emit, subscribe, domain event, CQRS.
---

# Event Handling Patterns

## Domain Events

| Event | Aggregate | Payload | Handlers |
|-------|-----------|---------|----------|
{{EVENTS_TABLE}}

## Event Emission Pattern

```{{LANGUAGE}}
{{EVENT_EMISSION_PATTERN}}
```

## Handler Pattern

```{{LANGUAGE}}
{{EVENT_HANDLER_PATTERN}}
```

## Event Subscription

```{{LANGUAGE}}
{{SUBSCRIPTION_PATTERN}}
```

## Event Flow

```
{{AGGREGATE}} 
  → emits {{EVENT}}
    → handled by {{HANDLER}}
      → updates {{TARGET}}
```

## Anti-Patterns

❌ **DON'T:** Modify aggregate state in handler
❌ **DON'T:** Throw exceptions in handlers (use dead letter)
❌ **DON'T:** Create circular event chains
```

---

## testing-patterns/ Skill (Enhanced)

**Source:** Gherkin tests, Pseudocode, Fitness Functions

```markdown
---
name: testing-patterns
description: Testing patterns with Gherkin templates for {{PROJECT_NAME}}. Use when writing tests, creating fixtures, or following TDD workflow. Keywords: test, Gherkin, scenario, fixture, TDD, coverage.
---

# Testing Patterns

## Available Features

| Feature | Scenarios | Coverage |
|---------|-----------|----------|
{{GHERKIN_FEATURES_TABLE}}

## Gherkin → Test Mapping

### Feature: {{FEATURE_NAME}}

```gherkin
{{EXAMPLE_GHERKIN}}
```

Maps to:

```{{LANGUAGE}}
{{TEST_IMPLEMENTATION}}
```

## Given → Setup Patterns

| Given Step | Setup Code |
|------------|------------|
{{GIVEN_MAPPINGS}}

## When → Action Patterns

| When Step | Action Code |
|-----------|-------------|
{{WHEN_MAPPINGS}}

## Then → Assert Patterns

| Then Step | Assertion Code |
|-----------|----------------|
{{THEN_MAPPINGS}}

## Fixture Patterns

```{{LANGUAGE}}
{{FIXTURE_PATTERN}}
```

## Coverage Requirements (Fitness)

| Metric | Target |
|--------|--------|
| Line Coverage | {{LINE_TARGET}}% |
| Branch Coverage | {{BRANCH_TARGET}}% |
| Critical Paths | 100% |

## Test Data Builders

```{{LANGUAGE}}
{{TEST_BUILDER_PATTERN}}
```
```

---

## project-context/ Skill (Enhanced)

**Source:** .ai-context/*, Research Findings, PRD

```markdown
---
name: project-context
description: Full project context and domain knowledge for {{PROJECT_NAME}}. Use when needing business context, domain understanding, or project background. Keywords: context, domain, business, glossary, background.
---

# Project Context

## Overview

{{FROM_AI_CONTEXT_README}}

## Architecture Summary

{{FROM_AI_CONTEXT_ARCHITECTURE}}

## Key Decisions

{{FROM_AI_CONTEXT_KEY_DECISIONS}}

## Domain Glossary

| Term | Definition | Context |
|------|------------|---------|
{{FROM_AI_CONTEXT_GLOSSARY}}

## Bounded Contexts

{{FROM_AI_CONTEXT_BOUNDED_CONTEXTS}}

## Business Rules

{{KEY_BUSINESS_RULES}}

## User Personas

{{FROM_PRD_PERSONAS}}

## Success Metrics

{{FROM_PRD_METRICS}}
```

---

## coding-standards/ Skill (Enhanced)

**Source:** DDD Tactical, ADRs, .ai-context/coding-standards.md

```markdown
---
name: coding-standards
description: Coding standards with DDD patterns for {{PROJECT_NAME}}. Use when writing code, reviewing style, or applying project conventions. Keywords: style, convention, pattern, standard, {{TECH_KEYWORDS}}.
---

# Coding Standards

## From .ai-context

{{FROM_AI_CONTEXT_CODING_STANDARDS}}

## DDD Naming Conventions

| Element | Convention | Example |
|---------|------------|---------|
| Aggregate | PascalCase, noun | `OrderAggregate` |
| Entity | PascalCase, noun | `OrderItem` |
| Value Object | PascalCase, descriptive | `Money`, `Address` |
| Domain Event | PascalCase, past tense | `OrderPlaced` |
| Repository | I{Aggregate}Repository | `IOrderRepository` |
| Domain Service | {Action}Service | `PricingService` |

## File Organization (DDD)

```
src/
├── domain/
│   ├── {context}/
│   │   ├── aggregates/
│   │   ├── entities/
│   │   ├── value-objects/
│   │   ├── events/
│   │   ├── repositories/
│   │   └── services/
│   └── shared/
├── application/
│   └── {context}/
│       ├── commands/
│       ├── queries/
│       └── handlers/
└── infrastructure/
    └── {context}/
        ├── persistence/
        └── messaging/
```

## ADR-Based Standards

{{CODING_STANDARDS_FROM_ADRS}}

## Anti-Patterns

{{ANTI_PATTERNS_FROM_REJECTED_ADRS}}
```

---

## Fill Instructions

### For aggregate-patterns/

1. From `docs/ddd/tactical/aggregates/`:
   - List all aggregates with descriptions
   - Extract invariant rules
   - Identify common patterns

2. Generate language-specific templates based on Architecture.md tech stack

### For event-handlers/

1. From `docs/ddd/tactical/events/`:
   - List all events with aggregates
   - Extract handler patterns
   - Map event flows

### For testing-patterns/

1. From `docs/tests/*.feature`:
   - Index all features
   - Extract Given/When/Then patterns
   - Map to test implementations

2. From `docs/fitness/`:
   - Coverage requirements

### For project-context/

1. Direct integration from `.ai-context/`:
   - README.md → Overview
   - architecture-summary.md → Architecture
   - key-decisions.md → Key Decisions
   - domain-glossary.md → Glossary
   - bounded-contexts.md → Contexts

### For coding-standards/

1. From `.ai-context/coding-standards.md`:
   - Direct integration

2. From `docs/adr/`:
   - Extract coding-related decisions
   - Extract rejected alternatives as anti-patterns
