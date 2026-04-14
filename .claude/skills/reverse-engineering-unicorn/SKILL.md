---
name: reverse-engineering-unicorn
description: Reverse engineer any company into a launch playbook with clickable CJM prototype. Triggers on "проанализируй компанию", "reverse engineer", "разбери бизнес-модель", "playbook запуска".
---

# Reverse Engineering Unicorn v2

Модульный reverse engineering компаний для создания actionable launch playbook.
7 модулей × 3 режима глубины × checkpoints × кликабельный CJM прототип.

## When To Activate

Trigger on:
- "проанализируй компанию [X]"
- "reverse engineer [X]"
- "разбери бизнес-модель [X]"
- "сделай playbook запуска аналога [X]"
- "проанализируй стартап [X]"

## Architecture

```
SKILL.md (this file — orchestrator)
├── modules/
│   ├── 01-intelligence.md            → Verified Fact Sheet
│   ├── 02-product-customers.md       → JTBD + Segments + Voice of Customer
│   ├── 025-cjm-prototype.md          → 3 CJM variants → clickable React prototype
│   ├── 03-market-competition.md      → TAM/SAM + Game Theory + TRIZ
│   ├── 04-business-finance.md        → Unit Economics + P&L + Sensitivity
│   ├── 05-growth-engine.md           → Growth Loop + Moats + 2nd-Order
│   └── 06-playbook-synthesis.md      → 90-Day Plan + BS-check
├── references/
│   ├── jtbd-canvas.md                → JTBD template
│   ├── blue-ocean-canvas.md          → Strategy Canvas template
│   └── industry-benchmarks.md        → Unit economics benchmarks
└── examples/
    ├── noom-module1-example.md        → Few-shot for Module 1
    └── noom-cjm-example.md            → Few-shot: .jsx structure for CJM
```

## External Skills (loaded via view() in DEEP/VERIFIED modes)

| Skill | Modules | Purpose |
|-------|---------|---------|
| `explore` | Pre-flight | Clarify vague requests |
| `goap-research-ed25519` | M1-M5 (DEEP) | Adaptive research: A* + OODA |
| `goap-research-ed25519` | M1-M5 (VERIFIED) | + Ed25519 crypto verification |
| `problem-solver-enhanced` | M3,M4,M5 (DEEP) | Game Theory, TRIZ, 2nd-Order |
| `frontend-design` | M2.5 (DEEP) | Production-grade CJM prototype design |
| `brutal-honesty-review` | M6 (DEEP) | BS-detection quality gate |
| `presentation-storyteller` | Post-M6 | Pitch deck generation |
| `idea2prd-manual` | Post-M6 | PRD for development |
| `md2pptx` | Post-M6 | Convert .md → .pptx |

## Three Modes

| Mode | Research | Analysis | Confidence | Time |
|------|----------|----------|------------|------|
| 🟢 QUICK | Static queries | Templates only | Manual X/5 | ~70 min |
| 🔵 DEEP | GOAP A*+OODA | +GT, TRIZ, 2nd-Order, CJM proto, BS-check | Formula | ~140 min |
| 🟣 VERIFIED | GOAP+Ed25519 | +Crypto signatures, audit trail | +Trusted issuers | ~170 min |

## Pipeline

```
INPUT: {COMPANY}, {URL}, {INDUSTRY}, {GEOGRAPHY}, {MODE}
                      ↓
  MODULE 0: PRE-FLIGHT (if variables unclear → explore skill)
  ⏸️ CHECKPOINT 0
                      ↓
  MODULE 1: INTELLIGENCE → Verified Fact Sheet
  ⏸️ CHECKPOINT 1
                      ↓
  MODULE 2: PRODUCT & CUSTOMERS → JTBD + Segments + Voice
  ⏸️ CHECKPOINT 2
                      ↓
  MODULE 2.5: CJM PROTOTYPE → 3 variants as clickable React app
    • User explores A/B/C variants
    • User compares (⚖️), builds custom mix (🔧), previews (👁)
    • User locks winning CJM (✅) → {CHOSEN_CJM}
  ⏸️ CHECKPOINT 2.5
                      ↓
  MODULE 3: MARKET & COMPETITION → TAM/SAM + Game Theory + TRIZ
    (uses {CHOSEN_CJM} for competitive Aha comparison)
  ⏸️ CHECKPOINT 3
                      ↓
  MODULE 4: BUSINESS & FINANCE → Unit Economics + P&L
    (uses {CHOSEN_CJM} paywall timing for revenue model)
  ⏸️ CHECKPOINT 4
                      ↓
  MODULE 5: GROWTH ENGINE → Loop + Channels + Moats
    (uses {CHOSEN_CJM} core loop for growth strategy)
  ⏸️ CHECKPOINT 5
                      ↓
  MODULE 6: PLAYBOOK SYNTHESIS → 90-Day Plan + BS-check
    (MVP scope = {CHOSEN_CJM} screens)
  ⏸️ CHECKPOINT 6 (FINAL)
                      ↓
  POST: presentation-storyteller / md2pptx / idea2prd-manual
```

## Execution Protocol

### Step 0: Extract Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `{COMPANY}` | Company name | Calendly |
| `{URL}` | Website | https://calendly.com |
| `{INDUSTRY}` | Industry | Scheduling / Productivity |
| `{GEOGRAPHY}` | Launch geography | Россия |
| `{MODE}` | Analysis mode | QUICK / DEEP / VERIFIED |

If variables unclear → `view` the `explore` skill.

### Steps 1-6: Sequential Module Execution

For each module:
1. `view` the module file from `modules/`
2. Substitute {COMPANY}, {URL}, {INDUSTRY}, {GEOGRAPHY}, {MODE}
3. Execute Research Protocol for selected {MODE}
4. In DEEP/VERIFIED — `view()` external skills listed in module
5. `view` any `references/*.md` or `examples/*.md` referenced
6. Generate structured output per module template
7. Show CHECKPOINT, wait for user command
8. On "ок" → next module

### Module 2.5 Special: CJM Prototype

This module **GENERATES a new React .jsx file** for every company.
It does NOT show a hardcoded Noom prototype.

Flow:
1. Extract CJM building blocks from M2 output
2. Generate 3 variant hypotheses (different Aha × Entry × Paywall)
3. Write .jsx with variant switcher, comparison, builder, scoring
4. User explores → customizes → locks winning CJM
5. `{CHOSEN_CJM}` feeds into M3-M6

The `examples/noom-cjm-example.md` is a few-shot for CODE STRUCTURE only.

### Step 7: Deliver

After CHECKPOINT 6:
1. Compile all outputs into one document
2. Create .md file, present to user
3. Offer next steps: pitch deck / PRD / pptx

## Checkpoint Commands (all modules)

| Command | Action |
|---------|--------|
| `ок` / `далее` | Next module |
| `глубже [topic]` | Additional research |
| `скорректируй [what]` | Fix output |
| `переключи на DEEP` | Rebuild in DEEP mode |
| `переключи на VERIFIED` | Rebuild with Ed25519 |
| `пропусти` | Skip to next |
| `стоп` | Save state |
| `сначала` | Restart current module |

## Module 2.5 Extra Commands

| Command | Action |
|---------|--------|
| `выбираю A/B/C` | Lock variant → M3 |
| `собираю свой` | Open builder (mix & match) |
| `ещё вариант: [идея]` | Add variant D |
| `объедини A+C` | Hybrid variant |
| `другой Aha в B: [что]` | Rebuild variant B |
| `перерисуй [screen]` | Change one screen |
| `без overlay` | Clean prototype for showing clients |

## Anti-Hallucination Rules (ALL modes)

1. **Search First** — never answer from memory for facts
2. **Source Attribution** — every fact → URL
3. **НЕ НАЙДЕНО > fabrication** — no data = "НЕ НАЙДЕНО"
4. **Hypotheses marked** — `[H]` tag on unverified claims
5. **Confidence Score** — end of every module

## Module → Skill Mapping

```
M0:   explore
M1:   goap-research-ed25519
M2:   goap-research-ed25519 + references/jtbd-canvas.md
M2.5: frontend-design + examples/noom-cjm-example.md (GENERATES new .jsx)
M3:   goap-research-ed25519 + problem-solver-enhanced [GT, TRIZ, 2nd-Order]
M4:   goap-research-ed25519 + problem-solver-enhanced [FP, TRIZ] + references/industry-benchmarks.md
M5:   goap-research-ed25519 + problem-solver-enhanced [2nd-Order, TRIZ]
M6:   brutal-honesty-review [Bach + Ramsay]
Post: presentation-storyteller / md2pptx / idea2prd-manual
```
