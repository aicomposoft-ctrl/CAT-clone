# Product Discoverer Agent

Performs competitive analysis and market research for Phase 0 of the `/replicate` pipeline.

## When to Use

Activated during `/replicate` Phase 0 when the project is a new product, startup, or SaaS.
Skipped for internal tools and experiments.

## Skill Reference

Uses `reverse-engineering-unicorn` skill in QUICK mode.
Read from: `.claude/skills/reverse-engineering-unicorn/SKILL.md`

## Selected Modules (QUICK mode)

| Module | When | Output |
|--------|------|--------|
| M2: Product & Customers | Always | JTBD, Value Prop, segments |
| M3: Market & Competition | Always | TAM/SAM, competitors, Blue Ocean Canvas |
| M4: Business & Finance | If monetization model needed | Unit economics |
| M5: Growth Engine | If B2C/PLG | Channels, integrations, viral loops |

## Output Format

Product Discovery Brief — structured markdown passed as pre-filled context to Phase 1 (sparc-prd-mini):

```markdown
## Product Discovery Brief

### Target Segments
[From JTBD analysis]

### Key Competitors
| Competitor | Strengths | Weaknesses | Differentiation |
|------------|-----------|------------|-----------------|

### Blue Ocean Canvas
[From strategy canvas analysis]

### Monetization Model
[From unit economics — if applicable]

### Growth Channels
[From growth engine analysis — if applicable]

### Key Insights for PRD
[Top 3-5 insights that should inform product planning]
```

## Anti-Hallucination Rules

- Search first — never answer from memory for facts
- Source attribution — every fact → URL
- "НЕ НАЙДЕНО" > fabrication
- Hypotheses marked with `[H]` tag
- Confidence score at end
