# Harvest Report Template

Generated at the end of a harvest session. Summarizes what was extracted.

---

```markdown
# Harvest Report: {{PROJECT_NAME}}

**Date:** {{YYYY-MM-DD}}
**Mode:** {{QUICK / FULL}}
**Duration:** {{N}} minutes

## Summary

| Metric | Value |
|--------|-------|
| Files scanned | {{N}} |
| TOOLKIT_HARVEST.md markers | {{M}} |
| Candidates found (Phase 1) | {{K}} |
| Classified for extraction (Phase 2) | {{J}} |
| Successfully decontextualized (Phase 3) | {{L}} |
| Integrated into toolkit (Phase 4) | {{I}} |
| Skipped (with reasons) | {{S}} |

## Extracted Artifacts

| # | Name | Category | Maturity | Version | Location |
|---|------|----------|----------|---------|----------|
| 1 | {{name}} | {{cat}} | 🔴 Alpha | v1.0 | {{path}} |
| 2 | {{name}} | {{cat}} | 🟡 Beta | v2.1 | {{path}} |

### By Category

| Category | Count | New | Updated |
|----------|-------|-----|---------|
| Skills | {{N}} | {{X}} | {{Y}} |
| Commands | {{N}} | {{X}} | {{Y}} |
| Hooks | {{N}} | {{X}} | {{Y}} |
| Rules | {{N}} | {{X}} | {{Y}} |
| Templates | {{N}} | {{X}} | {{Y}} |
| Patterns | {{N}} | {{X}} | {{Y}} |
| Snippets | {{N}} | {{X}} | {{Y}} |

## Skipped Items

| # | Name | Reason |
|---|------|--------|
| 1 | {{name}} | {{reason}} |

## Toolkit Status (after harvest)

| Maturity | Count |
|----------|-------|
| 🔴 Alpha | {{N}} |
| 🟡 Beta | {{M}} |
| 🟢 Stable | {{K}} |
| ⭐ Proven | {{J}} |
| **Total** | **{{T}}** |

## Recommendations

- {{Recommendation 1 — e.g., "Promote X to Beta after next project use"}}
- {{Recommendation 2 — e.g., "Pattern Y needs Rust variant"}}
- {{Recommendation 3 — e.g., "Consider merging A and B into single pattern"}}

## Next Harvest

Suggested after: {{next project/sprint/milestone}}
```
