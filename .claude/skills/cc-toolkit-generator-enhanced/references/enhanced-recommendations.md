# Enhanced Recommendations Engine

Smart recommendation rules for idea2prd-manual documents.

## Detection Phase

### Pipeline Detection

```python
def detect_pipeline(uploads_path: str) -> str:
    """Detect source documentation pipeline."""
    
    has_ddd = exists(f"{uploads_path}/docs/ddd/")
    has_ai_context = exists(f"{uploads_path}/.ai-context/")
    has_gherkin = glob(f"{uploads_path}/docs/tests/*.feature")
    has_adr = len(glob(f"{uploads_path}/docs/adr/*.md")) > 5
    has_sparc = exists(f"{uploads_path}/Architecture.md")
    
    if has_ddd and has_ai_context:
        return "IDEA2PRD_FULL"  # Complete idea2prd-manual output
    elif has_ddd or has_adr:
        return "IDEA2PRD_PARTIAL"  # Partial idea2prd output
    elif has_sparc:
        return "SPARC"  # SPARC-only documentation
    else:
        return "MINIMAL"  # Basic PRD only
```

## Scoring Rules

### Base Scores by Pipeline

| Pipeline | Base Score | Additional Features |
|----------|------------|---------------------|
| IDEA2PRD_FULL | +20 | All DDD agents, all skills |
| IDEA2PRD_PARTIAL | +15 | Core DDD agents |
| SPARC | +10 | Standard agents |
| MINIMAL | +5 | Basic agents only |

---

## DDD-Specific Recommendations

### domain-expert.md Agent

```python
score = 5  # base

if exists("docs/ddd/strategic/bounded-contexts.md"):
    score += 10
    
if exists(".ai-context/domain-glossary.md"):
    score += 5
    terms = count_terms(".ai-context/domain-glossary.md")
    if terms > 20:
        score += 3
        
if exists(".ai-context/bounded-contexts.md"):
    score += 5

# RECOMMEND if score >= 15
```

### ddd-validator.md Agent

```python
score = 5  # base

aggregates = glob("docs/ddd/tactical/aggregates/*.md")
if len(aggregates) > 3:
    score += 8
if len(aggregates) > 7:
    score += 5

if exists("docs/fitness/fitness-functions.md"):
    score += 5
    functions = count_functions("docs/fitness/fitness-functions.md")
    if functions > 5:
        score += 3

# RECOMMEND if score >= 15
```

### aggregate-patterns/ Skill

```python
score = 5  # base

aggregates = glob("docs/ddd/tactical/aggregates/*.md")
if len(aggregates) > 0:
    score += 8
    
entities = glob("docs/ddd/tactical/entities/*.md")
if len(entities) > 0:
    score += 3
    
value_objects = glob("docs/ddd/tactical/value-objects/*.md")
if len(value_objects) > 0:
    score += 3

# RECOMMEND if score >= 12
```

### event-handlers/ Skill

```python
score = 5  # base

events = glob("docs/ddd/tactical/events/*.md")
if len(events) > 0:
    score += 10
if len(events) > 5:
    score += 5

# RECOMMEND if score >= 12
```

---

## ADR-Specific Recommendations

### architect.md Agent (Enhanced)

```python
score = 10  # base (always somewhat useful)

adrs = glob("docs/adr/*.md")
if len(adrs) > 5:
    score += 5
if len(adrs) > 10:
    score += 5
if len(adrs) > 15:
    score += 3

if exists("docs/c4/context.mermaid"):
    score += 3
if exists("docs/c4/container.mermaid"):
    score += 3

# RECOMMEND if score >= 15
```

### Security Rules Boost

```python
security_boost = 0

for adr in glob("docs/adr/*.md"):
    content = read(adr)
    if "security" in content.lower():
        security_boost += 2
    if "authentication" in content.lower():
        security_boost += 1
    if "encryption" in content.lower():
        security_boost += 1

# Apply boost to security.md rule score
```

---

## Gherkin-Specific Recommendations

### testing-patterns/ Skill (Enhanced)

```python
score = 5  # base

features = glob("docs/tests/*.feature")
if len(features) > 0:
    score += 10
    
total_scenarios = 0
for feature in features:
    total_scenarios += count_scenarios(feature)
    
if total_scenarios > 10:
    score += 5
if total_scenarios > 20:
    score += 3

# RECOMMEND if score >= 12
```

### tdd-guide.md Agent (Enhanced)

```python
score = 5  # base

if glob("docs/tests/*.feature"):
    score += 5
    
if glob("docs/pseudocode/*.pseudo"):
    score += 5
    
if exists("docs/fitness/fitness-functions.md"):
    content = read("docs/fitness/fitness-functions.md")
    if "coverage" in content.lower():
        score += 3

# RECOMMEND if score >= 12
```

### /test Command

```python
score = 10  # base (always useful)

features = glob("docs/tests/*.feature")
if len(features) > 0:
    score += 10  # Highly recommended with Gherkin

# RECOMMEND if score >= 15
```

---

## Pseudocode-Specific Recommendations

### planner.md Agent (Enhanced)

```python
score = 10  # base

pseudo_files = glob("docs/pseudocode/*.pseudo")
if len(pseudo_files) > 0:
    score += 8
if len(pseudo_files) > 5:
    score += 5

total_lines = 0
for pseudo in pseudo_files:
    total_lines += count_lines(pseudo)
    
if total_lines > 200:
    score += 3

# RECOMMEND if score >= 15
```

---

## Fitness-Specific Recommendations

### Validation Hooks

```python
score = 5  # base

if exists("docs/fitness/fitness-functions.md"):
    score += 8
    
    content = read("docs/fitness/fitness-functions.md")
    functions = parse_fitness_functions(content)
    
    for func in functions:
        if func.automated:
            score += 2

# RECOMMEND if score >= 12
```

### /validate-ddd Command

```python
score = 5  # base

if exists("docs/fitness/fitness-functions.md"):
    score += 5
    
if exists("docs/ddd/tactical/"):
    score += 5
    
aggregates = glob("docs/ddd/tactical/aggregates/*.md")
if len(aggregates) > 3:
    score += 5

# RECOMMEND if score >= 12
```

---

## .ai-context Integration Scoring

### project-context/ Skill

```python
score = 5  # base

ai_context_files = [
    ".ai-context/README.md",
    ".ai-context/architecture-summary.md",
    ".ai-context/key-decisions.md",
    ".ai-context/domain-glossary.md",
    ".ai-context/bounded-contexts.md",
    ".ai-context/coding-standards.md",
    ".ai-context/fitness-rules.md",
    ".ai-context/pseudocode-index.md"
]

found = sum(1 for f in ai_context_files if exists(f))
score += found * 2  # +2 per file found

# RECOMMEND if score >= 12 (need at least 4 files)
```

### CLAUDE.md Enhancement

```python
# If .ai-context exists, enhance CLAUDE.md integration
if exists(".ai-context/"):
    use_enhanced_template = True
    ai_context_priority = "HIGH"
else:
    use_enhanced_template = False
    ai_context_priority = "LOW"
```

---

## Priority Tier Assignment (Enhanced)

### Tier Rules

```python
def assign_tier(score: int, document_source: str) -> str:
    """Assign priority tier based on score and source."""
    
    # DDD documents get tier boost
    ddd_boost = 2 if document_source in ["DDD_STRATEGIC", "DDD_TACTICAL"] else 0
    
    # Gherkin documents get tier boost  
    gherkin_boost = 2 if document_source == "GHERKIN" else 0
    
    # .ai-context integration boost
    ai_context_boost = 3 if document_source == "AI_CONTEXT" else 0
    
    adjusted_score = score + ddd_boost + gherkin_boost + ai_context_boost
    
    if adjusted_score >= 18:
        return "P1"  # Highly recommended, default ON
    elif adjusted_score >= 12:
        return "P1"  # Recommended, default ON
    elif adjusted_score >= 8:
        return "P2"  # Optional, default OFF
    else:
        return "P3"  # External/advanced, default OFF
```

### Default Selections by Pipeline

| Pipeline | P1 (Default ON) | P2 (Optional) | P3 (Advanced) |
|----------|-----------------|---------------|---------------|
| IDEA2PRD_FULL | 12-15 instruments | 5-8 instruments | 2-4 instruments |
| IDEA2PRD_PARTIAL | 8-10 instruments | 4-6 instruments | 2-3 instruments |
| SPARC | 6-8 instruments | 3-4 instruments | 1-2 instruments |
| MINIMAL | 3-4 instruments | 2-3 instruments | 0-1 instruments |

---

## Output Format

### HYBRID Mode Checkpoint 1

```
═══════════════════════════════════════════════════════════════
⏸️ HYBRID CHECKPOINT 1: Smart Selection
═══════════════════════════════════════════════════════════════

📊 Pipeline Detected: IDEA2PRD_FULL
   Documents: 45 files across 8 categories

✅ P0 Generated (mandatory):
   • CLAUDE.md (enhanced with .ai-context)    4.2 KB
   • security.md (from 3 security ADRs)       1.8 KB
   • coding-style.md (from coding-standards)  2.1 KB
   • domain-model.md (from DDD Strategic)     1.5 KB  [NEW]

📦 P1 Recommended (score ≥12):

| # | Instrument | Type | Score | Source |
|---|------------|------|-------|--------|
| 1 | domain-expert.md | Agent | 23 | DDD Strategic + Glossary |
| 2 | planner.md | Agent | 21 | Pseudocode (8 files) |
| 3 | code-reviewer.md | Agent | 19 | Fitness + ADRs |
| 4 | ddd-validator.md | Agent | 18 | Aggregates (6) + Fitness |
| 5 | tdd-guide.md | Agent | 17 | Gherkin + Pseudocode |
| 6 | project-context/ | Skill | 21 | .ai-context (8 files) |
| 7 | coding-standards/ | Skill | 18 | coding-standards + ADRs |
| 8 | testing-patterns/ | Skill | 16 | Gherkin (12 scenarios) |
| 9 | aggregate-patterns/ | Skill | 15 | DDD Tactical |
| 10 | /plan | Command | 18 | Pseudocode |
| 11 | /test | Command | 20 | Gherkin features |
| 12 | testing.md | Rule | 15 | Fitness + Gherkin |

📦 P2 Optional (score 8-11):

| 13 | architect.md | Agent | 11 | C4 + ADRs |
| 14 | event-handlers/ | Skill | 10 | Domain Events (4) |
| 15 | /validate-ddd | Command | 11 | Fitness + DDD |
| 16 | settings.json | Hooks | 9 | Fitness automation |

📦 P3 External:

| 17 | .mcp.json | Config | - | GitHub, PostgreSQL |

⚡ Quick Actions:
• "ок" — generate all P1 (12 instruments)
• "минимум" — P0 only
• "максимум" — all P1 + P2 + P3 (17 instruments)
• "+ddd" — add all DDD-specific (domain-expert, ddd-validator, aggregate-patterns)
• "+gherkin" — add all Gherkin-specific (testing-patterns, /test, tdd-guide)
• "+N" / "-N" — toggle specific

═══════════════════════════════════════════════════════════════
```
