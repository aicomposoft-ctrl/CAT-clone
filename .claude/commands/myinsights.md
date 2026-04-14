# /myinsights — Knowledge Base Management

## Usage
```
/myinsights                  # Browse index
/myinsights capture          # Capture current insight
/myinsights search <keyword> # Search insights
/myinsights list             # List all insights with status
```

## Directory Structure

```
myinsights/
├── 1nsights.md              # Index: INS-NNN | title | category | status | hits
└── INS-001-slug.md          # Detail files (one per insight)
```

## Capture Flow

When `/myinsights capture` is triggered:

1. Identify what was just learned/solved
2. Check `myinsights/1nsights.md` — is this already captured? (update hit_count if yes)
3. If new: generate next INS-NNN ID
4. Write detail file: `myinsights/INS-NNN-<slug>.md`
5. Update index: `myinsights/1nsights.md`
6. Commit: `docs(insights): capture INS-NNN <short-title>`

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

## Index Format

```markdown
# CAT Insights Index

| ID | Title | Category | Status | Hits |
|----|-------|----------|--------|------|
| INS-001 | Alembic env.py missing model | database | Active | 3 |
```

## Error-First Lookup Protocol

**BEFORE debugging any issue, ALWAYS run:**
```bash
grep -r "KEYWORD" myinsights/
```

Never spend more than 5 minutes on an issue without checking here first.

## Trigger Conditions

Suggest `/myinsights capture` when:
- Bug fixed after >20 minutes
- Workaround discovered for undocumented behavior
- Integration pattern unlocked (connecting two systems)
- Performance optimization found
- Security pattern applied
