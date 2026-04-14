# Insights Capture Rule — CAT

## Error-First Lookup Protocol

**BEFORE debugging any issue, ALWAYS run:**
```bash
grep -r "KEYWORD" myinsights/
```

Never spend more than 5 minutes on an issue without checking the knowledge base first.

## When to Suggest Capturing an Insight

Suggest `/myinsights` capture when ANY of these occur:

1. **Bug fixed after >20 minutes** — the fix is non-obvious and will recur
2. **Workaround discovered** — something doesn't work as documented
3. **Integration pattern unlocked** — connecting two systems required undocumented steps
4. **Performance optimization found** — a specific tuning approach that worked
5. **Security pattern applied** — a specific way to handle auth/crypto/tenant isolation

**Prompt format:**
> "This looks like a reusable insight. Want to capture it with `/myinsights`?"

## When NOT to Suggest

Do NOT suggest capture when:
1. The issue is trivial and well-documented (typo, missing import)
2. The fix is already covered in existing `myinsights/` entry (check first)
3. The issue is environment-specific and won't recur
4. Mid-flow — wait until the fix is fully verified

## Insight Lifecycle

| Status | Meaning | Action |
|--------|---------|--------|
| `Active` | Currently valid, use freely | Apply directly |
| `Workaround` | Works but fragile, watch for updates | Apply with caution |
| `Obsolete` | No longer applies (library update, etc.) | Archive it |

When applying an insight: update `hit_count` in `myinsights/1nsights.md`

## Directory Structure

```
myinsights/
├── 1nsights.md           # Index: INS-NNN | title | category | status | hits
└── INS-001-slug.md       # Detail files (one per insight)
    INS-002-slug.md
    ...
```

## Insight Format

```markdown
# INS-NNN: Short Title

**Category:** [scraping|ml|database|api|frontend|devops|security]
**Status:** Active | Workaround | Obsolete
**Hit Count:** 0
**Date:** YYYY-MM-DD

## Problem
What went wrong or what challenge was faced.

## Solution
Exact fix or approach that worked. Include code snippets.

## Why It Works
Brief explanation of the root cause.

## Applies To
Which services/files/scenarios this affects.
```
