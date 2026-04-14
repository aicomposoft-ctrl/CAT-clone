# DDD-Specific Hooks & Commands Templates

Enhanced hooks and commands for DDD-aware Claude Code instruments.

---

## Fitness Function Hooks (settings.json)

**Source:** docs/fitness/fitness-functions.md

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/validate-aggregate-size.sh \"$CLAUDE_FILE_PATH\"",
            "timeout": 10
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "if [[ \"$CLAUDE_FILE_PATH\" == *aggregate* ]] || [[ \"$CLAUDE_FILE_PATH\" == *entity* ]]; then \"$CLAUDE_PROJECT_DIR\"/.claude/hooks/check-ddd-patterns.sh \"$CLAUDE_FILE_PATH\"; fi",
            "timeout": 30
          }
        ]
      },
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "if [[ \"$CLAUDE_FILE_PATH\" == *.test.* ]] || [[ \"$CLAUDE_FILE_PATH\" == *.spec.* ]]; then npm test -- --testPathPattern=\"$(basename $CLAUDE_FILE_PATH)\" --coverage 2>/dev/null || true; fi",
            "timeout": 120
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "prompt",
            "prompt": "Before stopping, verify: 1) All aggregate invariants enforced, 2) Domain events emitted for state changes, 3) Tests cover Gherkin scenarios, 4) Fitness functions pass.",
            "timeout": 30
          }
        ]
      }
    ]
  }
}
```

---

## Hook Scripts

### validate-aggregate-size.sh

```bash
#!/bin/bash
# Validates aggregate doesn't exceed size limits
# Source: Fitness Function FF-02

FILE="$1"
MAX_ENTITIES={{MAX_ENTITIES_FROM_FITNESS}}
MAX_METHODS={{MAX_METHODS_FROM_FITNESS}}

# Count entities (rough heuristic)
ENTITY_COUNT=$(grep -c "class.*Entity" "$FILE" 2>/dev/null || echo 0)

if [ "$ENTITY_COUNT" -gt "$MAX_ENTITIES" ]; then
    echo "❌ VIOLATION: Aggregate has $ENTITY_COUNT entities (max: $MAX_ENTITIES)"
    echo "Consider splitting into multiple aggregates"
    exit 1
fi

echo "✅ Aggregate size OK"
exit 0
```

### check-ddd-patterns.sh

```bash
#!/bin/bash
# Checks DDD patterns compliance
# Source: DDD Tactical docs

FILE="$1"
VIOLATIONS=0

# Check for direct entity modification
if grep -q "entity\." "$FILE" && ! grep -q "aggregate\." "$FILE"; then
    echo "⚠️ WARNING: Possible direct entity modification without aggregate"
    ((VIOLATIONS++))
fi

# Check for missing event emission after state change
if grep -q "this\.\w* =" "$FILE" && ! grep -q "emit\|publish\|dispatch" "$FILE"; then
    echo "⚠️ WARNING: State change without domain event"
    ((VIOLATIONS++))
fi

if [ "$VIOLATIONS" -gt 0 ]; then
    echo "Found $VIOLATIONS potential DDD violations"
fi

exit 0  # Warnings only, don't block
```

---

## /validate-ddd Command

**Source:** Fitness Functions, DDD Tactical

```markdown
---
description: Validate DDD patterns and fitness functions. $ARGUMENTS: scope (all|aggregate|context) or specific path.
---

# /validate-ddd $ARGUMENTS

## Purpose

Run DDD validation checks against project code, verifying aggregate boundaries, invariants, and fitness function compliance.

## Validation Checks

### Aggregate Validation
- [ ] Single aggregate root per file
- [ ] All modifications through aggregate root
- [ ] Invariants checked before state changes
- [ ] Events emitted for state changes

### Fitness Functions
{{FITNESS_FUNCTIONS_LIST}}

### Bounded Context Validation
- [ ] No cross-context direct dependencies
- [ ] Anti-corruption layers in place
- [ ] Shared kernel properly isolated

## Process

1. Parse $ARGUMENTS to determine scope
2. Scan relevant files
3. Run validation checks
4. Calculate fitness scores
5. Report violations with suggestions

## Examples

`/validate-ddd all` — Validate entire project
`/validate-ddd aggregate OrderAggregate` — Validate specific aggregate
`/validate-ddd context Orders` — Validate bounded context

## Output Format

```
═══════════════════════════════════════════
DDD Validation Report: {{SCOPE}}
═══════════════════════════════════════════

## Aggregates
✅ OrderAggregate: Valid
⚠️ CustomerAggregate: 2 warnings
❌ PaymentAggregate: 1 violation

## Fitness Functions
| Function | Target | Actual | Status |
|----------|--------|--------|--------|
| BC Independence | 100% | 98% | ⚠️ |
| Aggregate Size | ≤7 | 5 | ✅ |

## Violations
1. PaymentAggregate: Direct entity modification (line 45)
   Fix: Route through aggregate root method

## Score: 85/100
═══════════════════════════════════════════
```
```

---

## /test Command (Enhanced with Gherkin)

**Source:** Gherkin tests, Pseudocode

```markdown
---
description: Run or generate tests from Gherkin scenarios. $ARGUMENTS: feature name, scenario, or "all".
---

# /test $ARGUMENTS

## Purpose

Run existing tests or generate new tests from Gherkin feature files.

## Available Features

{{GHERKIN_FEATURES_LIST}}

## Process

1. Parse $ARGUMENTS:
   - Feature name → Run/generate for feature
   - Scenario name → Run/generate specific scenario
   - "all" → Run full test suite
   - "generate [feature]" → Generate tests from Gherkin

2. If generating:
   - Load feature file
   - Match with pseudocode
   - Generate test implementation
   
3. If running:
   - Execute test command
   - Report results with coverage

## Examples

`/test OrderPlacement` — Run OrderPlacement tests
`/test all` — Run all tests
`/test generate OrderPlacement` — Generate tests from feature
`/test "Successfully place order"` — Run specific scenario

## Gherkin → Test Example

From `docs/tests/order-placement.feature`:
```gherkin
Scenario: Successfully place order
  Given I am a verified customer
  And all items are in stock
  When I place the order
  Then the order should be created
  And I should receive confirmation
```

Generates:
```{{LANGUAGE}}
{{GENERATED_TEST_TEMPLATE}}
```

## Output Format

```
═══════════════════════════════════════════
Test Results: {{SCOPE}}
═══════════════════════════════════════════

✅ Passed: 12
❌ Failed: 1
⏭️ Skipped: 0

Coverage:
- Lines: 85%
- Branches: 78%

Failed:
- OrderPlacement > should handle out of stock
  Expected: OutOfStockError
  Actual: undefined
═══════════════════════════════════════════
```
```

---

## /deploy Command (Enhanced)

**Source:** COMPLETION_CHECKLIST.md

```markdown
---
description: Run deployment checklist and deploy to environment. $ARGUMENTS: environment (dev|staging|prod).
disable-model-invocation: true
---

# /deploy $ARGUMENTS

## Purpose

Execute deployment workflow following COMPLETION_CHECKLIST.md.

## Pre-Deployment Checklist

{{FROM_COMPLETION_CHECKLIST}}

## Environments

| Env | Requires | Auto-approve |
|-----|----------|--------------|
| dev | Tests pass | Yes |
| staging | Tests + Review | Yes |
| prod | All checks + Manual | No |

## Process

1. Parse $ARGUMENTS for target environment
2. Run pre-deployment checklist:
   - [ ] Tests pass
   - [ ] Fitness functions pass
   - [ ] DDD validation clean
   - [ ] Security scan clean
   - [ ] Build succeeds
3. Execute deployment:
   - dev: Auto-deploy
   - staging: Deploy after checks
   - prod: Require explicit confirmation
4. Run post-deployment verification

## Examples

`/deploy dev` — Deploy to development
`/deploy staging` — Deploy to staging with checks
`/deploy prod` — Production deployment (requires confirmation)

## Output Format

```
═══════════════════════════════════════════
Deployment: {{ENVIRONMENT}}
═══════════════════════════════════════════

## Pre-Deployment Checks
✅ Tests: Passed (45/45)
✅ Fitness: 95/100
✅ DDD: Valid
✅ Security: Clean
✅ Build: Success

## Deployment
🚀 Deploying to {{ENVIRONMENT}}...
✅ Deployment complete

## Post-Deployment
✅ Health check: Passed
✅ Smoke tests: Passed

## Summary
Deployed: v1.2.3
Time: 2m 34s
URL: https://{{ENVIRONMENT}}.example.com
═══════════════════════════════════════════
```
```

---

## /context Command (NEW)

**Source:** .ai-context/, DDD Strategic

```markdown
---
description: Show or switch project context. $ARGUMENTS: context name or "list".
---

# /context $ARGUMENTS

## Purpose

Navigate bounded contexts and show relevant domain information.

## Available Contexts

{{BOUNDED_CONTEXTS_LIST}}

## Process

1. Parse $ARGUMENTS:
   - "list" → Show all contexts
   - Context name → Show context details
   - Empty → Show current context

2. Display:
   - Context responsibilities
   - Aggregates in context
   - Related contexts (upstream/downstream)
   - Key domain events

## Examples

`/context list` — List all bounded contexts
`/context Orders` — Show Orders context details
`/context` — Show current context

## Output Format

```
═══════════════════════════════════════════
Bounded Context: Orders
═══════════════════════════════════════════

## Responsibilities
- Order placement and management
- Order fulfillment tracking
- Order history

## Aggregates
- OrderAggregate
- OrderItemEntity
- ShippingAddressVO

## Domain Events
- OrderPlaced
- OrderShipped
- OrderCancelled

## Relationships
- Upstream: Customers (Customer data)
- Downstream: Shipping (Fulfillment)

## Key Invariants
- Order total must match item sum
- Cannot modify shipped orders
═══════════════════════════════════════════
```
```

---

## Rules Templates (DDD-Enhanced)

### domain-model.md Rule

**Source:** DDD Strategic, DDD Tactical

```markdown
# Domain Model Rules

## Bounded Context Rules

- **DO:** Keep aggregates within single bounded context
- **DO:** Use anti-corruption layer for cross-context calls
- **DO:** Define clear context boundaries in code structure
- **DON'T:** Share entities across bounded contexts
- **DON'T:** Directly call into another context's aggregates

## Aggregate Rules

- **DO:** Modify entities only through aggregate root
- **DO:** Check invariants before state changes
- **DO:** Emit domain events for significant state changes
- **DO:** Keep aggregates small (≤{{MAX_ENTITIES}} entities)
- **DON'T:** Reference other aggregate roots directly
- **DON'T:** Perform I/O inside aggregate methods

## Entity Rules

- **DO:** Use value objects for identity
- **DO:** Implement equals based on identity only
- **DON'T:** Create entities without aggregate context

## Value Object Rules

- **DO:** Make all properties immutable
- **DO:** Implement equals on all properties
- **DO:** Validate in constructor
- **DON'T:** Include identity (ID) in value objects
- **DON'T:** Add setter methods

## Domain Event Rules

- **DO:** Use past tense naming (OrderPlaced, not PlaceOrder)
- **DO:** Include aggregate ID in event
- **DO:** Make event payload immutable
- **DO:** Include timestamp
- **DON'T:** Include behavior in events

## Rationale

Following DDD tactical patterns ensures:
- Clear boundaries and ownership
- Consistent transactional boundaries
- Auditable state changes
- Loose coupling between contexts
```

### fitness-functions.md Rule

**Source:** docs/fitness/fitness-functions.md

```markdown
# Fitness Functions

## Architecture Fitness

| ID | Rule | Target | Automated |
|----|------|--------|-----------|
{{FITNESS_FUNCTIONS_TABLE}}

## Validation Commands

Run validation:
```bash
/validate-ddd all
```

## Thresholds

| Metric | Warning | Error |
|--------|---------|-------|
| BC Independence | <95% | <90% |
| Aggregate Size | >5 | >7 |
| Method Complexity | >10 | >15 |
| Test Coverage | <80% | <70% |

## Rationale

Fitness functions provide automated architectural governance, ensuring the system maintains desired qualities as it evolves.
```
