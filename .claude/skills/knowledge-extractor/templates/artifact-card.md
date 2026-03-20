# Artifact Card Template

Universal documentation format for any toolkit artifact.
Replace all `{{PLACEHOLDERS}}` with actual content.

---

```markdown
# {{CATEGORY}}: {{ARTIFACT_NAME}}

## Maturity: {{🔴/🟡/🟢/⭐}} {{Alpha/Beta/Stable/Proven}}
## Used in: {{source-project}}
## Extracted: {{YYYY-MM-DD}}
## Last updated: {{YYYY-MM-DD}}
## Version: v{{MAJOR}}.{{MINOR}}

## When to Use

{{Conditions where this artifact is valuable.}}

## When NOT to Use

{{Explicit anti-conditions. When this is the wrong choice.}}

## Prerequisites

{{What must exist before using this artifact.}}
- {{Prerequisite 1}}
- {{Prerequisite 2}}

## Implementation

{{The actual artifact content — code, config, pattern description, etc.}}

## Variants

### Variant A: {{Context/Language/Framework}}

{{Alternative implementation for different context.}}

### Variant B: {{Context/Language/Framework}}

{{Another alternative.}}

## Gotchas

{{Things that can go wrong. Edge cases. Common mistakes.}}

- {{Gotcha 1}}
- {{Gotcha 2}}

## Related Artifacts

- {{Related artifact 1}} — {{relationship}}
- {{Related artifact 2}} — {{relationship}}

## Changelog
- v{{N}}: {{What changed and why}}
- v1: Initial extraction from {{source-project}}
```
