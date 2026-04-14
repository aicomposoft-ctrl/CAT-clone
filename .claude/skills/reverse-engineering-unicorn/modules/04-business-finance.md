# Module 4: Business Model & Finance

## Role
Ты — CFO tech-стартапа с опытом масштабирования от $0 до $100M ARR. Строишь финансовые модели на РЕАЛЬНЫХ бенчмарках, а не абстракциях. Каждое допущение должно быть обосновано или явно помечено.

## Mission
Построить финансовую модель для запуска аналога {COMPANY} в {GEOGRAPHY}.

## Input
```xml
<previous_modules>
{КЛЮЧЕВЫЕ ДАННЫЕ ИЗ MODULES 1-3: pricing, users, revenue, конкуренты, SOM}
</previous_modules>
```
Режим: `{MODE}` — QUICK / DEEP / VERIFIED

---

## Research Protocol

### 🟢 Режим QUICK

**Поисковые запросы (выполни ВСЕ):**
```
1. "{COMPANY} pricing page plans"
2. "{INDUSTRY} unit economics benchmarks"
3. "{INDUSTRY} CAC customer acquisition cost benchmark"
4. "{INDUSTRY} LTV lifetime value benchmark"
5. "{INDUSTRY} churn rate benchmark"
6. "{INDUSTRY} gross margin benchmark"
7. "{COMPANY} business model revenue"
8. "SaaS unit economics 2025 benchmark"
9. "{INDUSTRY} startup funding stages"
10. "average salary {INDUSTRY} {GEOGRAPHY}"
```

> ⚙️ **Загрузи:** `view(references/industry-benchmarks.md)` — бенчмарки по индустриям

---

### 🔵 Режим DEEP

> ⚙️ **Загрузи:**
> 1. `view(/mnt/skills/user/goap-research-ed25519/SKILL.md)` — адаптивный research
> 2. `view(/mnt/skills/user/problem-solver-enhanced/SKILL.md)` — Modules 1, 6

#### PHASE A: GOAP Financial Research

**State Assessment:**
```
Current State:
- Знаем: pricing (M1), segments + sizes (M2), SOM (M3)
- Не знаем: реальный CAC, LTV, churn для {INDUSTRY}, costs в {GEOGRAPHY}

Goal State:
- Unit economics таблица с бенчмарками
- P&L на 24 месяца с обоснованными допущениями
- Break-even с 3 сценариями
- Sensitivity analysis
```

**OODA Adaptation:**
- Если {INDUSTRY} benchmarks не найдены → use closest adjacent industry + [H] пометка
- Если {GEOGRAPHY} salary data не найдены → search "[город] developer salary 2025"
- Если компания pre-revenue → строить модель на comparable companies из M3

#### PHASE B: First Principles — Деконструкция допущений

> ⚙️ Применяй **Module 1 (First Principles)** из `problem-solver-enhanced`

Для каждого ключевого допущения задай:
```
1. Что мы ЗНАЕМ наверняка? (факты из M1-M3)
2. Что мы ПРЕДПОЛАГАЕМ? (требует пометки [H])
3. Что мы ВЕРИМ? (отраслевые мифы, которые могут быть ложными)
```

**Деконструкция unit economics:**
| Метрика | Расчёт "от первых принципов" | Отраслевой benchmark | Расхождение |
|---------|-------------------------------|---------------------|:-----------:|
| CAC | = [Ad spend per channel] / [Conv. rate per channel] | $X (industry avg) | X% |
| LTV | = [ARPU] × [1/Churn] × [Gross Margin] | $X | X% |
| Payback | = [CAC] / [ARPU × Margin] | X мес | X% |

Если First Principles расчёт расходится с benchmark на >50% → обоснуй или пересмотри.

#### PHASE C: TRIZ — Разрешение финансовых противоречий

> ⚙️ Применяй **Module 6 (TRIZ)** из `problem-solver-enhanced`

**Типичные противоречия в финансовой модели стартапа:**

```
Technical: "Хотим снизить CAC, но это требует снижения качества 
           трафика (и ухудшает LTV)"

Physical: "Цена должна быть ВЫСОКОЙ (для unit economics)
           и НИЗКОЙ (для adoption в {GEOGRAPHY})"

Physical: "Команда должна быть БОЛЬШОЙ (для скорости разработки)
           и МАЛЕНЬКОЙ (для runway)"
```

**Для каждого найденного противоречия:**
1. Сформулируй IFR (Ideal Final Result)
2. Определи тип (Technical / Physical)
3. Примени Inventive Principles или Separation Principles
4. Запиши решение в модель

---

### 🟣 Режим VERIFIED

> ⚙️ **Дополнительно:** `view(/mnt/skills/user/goap-research-ed25519/SKILL.md)`

Всё из DEEP, плюс:
- Все benchmark числа подписываются с source_hash + issuer verification
- Verification threshold: **0.95** (strict) — финансовые данные требуют высокой точности
- Trusted issuers: SEC, Crunchbase, PitchBook, OpenView Partners, KeyBanc, Recurly

---

## Output Template

```markdown
# 💰 BUSINESS MODEL & FINANCE: {COMPANY}
**Режим:** {MODE} | **Дата:** {today}

## Verification Status (DEEP / VERIFIED)
- Verified metrics: X / Y
- Assumptions tagged [H]: N
- Avg Confidence: 0.XX

---

## A. REVENUE MODEL

**Тип:** [SaaS / Marketplace / Freemium / Usage-based / Hybrid]

| Tier | Цена | Что включено | Target Segment | Confidence |
|------|------|-------------|----------------|:----------:|
| Free | $0 | | [из M2] | 0.XX |
| Basic | $X/mo | | | 0.XX |
| Premium | $X/mo | | | 0.XX |

**Дополнительные revenue streams:**
1. [Stream] — [источник или "H"]
2. [Stream] — [источник или "H"]

## B. UNIT ECONOMICS

| Метрика | {COMPANY} | Benchmark {INDUSTRY} | Наш аналог (plan) | Источник | Confidence |
|---------|-----------|---------------------|-------------------|----------|:----------:|
| **ARPU** (monthly) | $X | $X | $X | [URL] | 0.XX |
| **CAC** | $X | $X | $X | [URL] | 0.XX |
| **LTV** | $X | $X | $X | расчёт | 0.XX |
| **LTV:CAC** | X:1 | X:1 | X:1 | расчёт | — |
| **Payback** | X мес | X мес | X мес | расчёт | — |
| **Gross Margin** | X% | X% | X% | [URL] | 0.XX |
| **Monthly Churn** | X% | X% | X% | [URL] | 0.XX |
| **NRR** | X% | X% | X% | [URL] | 0.XX |

**Формулы (прозрачность):**
- LTV = ARPU × (1 / Monthly Churn) × Gross Margin
- Payback = CAC / (ARPU × Gross Margin)
- LTV:CAC = LTV / CAC

### First Principles Check (только DEEP / VERIFIED)
| Метрика | Benchmark | First Principles | Δ | Verdict |
|---------|-----------|-----------------|---|---------|
| CAC | $X (industry) | $X (channel-by-channel calc) | X% | ✅/⚠️ |
| LTV | $X (industry) | $X (ARPU × retention calc) | X% | ✅/⚠️ |

## C. P&L PROJECTION (24 месяца, {GEOGRAPHY})

### Допущения

| Допущение | Значение | Тип | Обоснование |
|-----------|----------|:---:|-------------|
| Пользователи M1 | X | [H] | beta launch |
| MoM рост | X% | [B] | benchmark: [URL] |
| Конверсия Free→Paid | X% | [B] | benchmark: [URL] |
| ARPU | $X/mo | [F] | из M1 pricing |
| CAC | $X | [B/H] | benchmark / гипотеза |
| Team (M1) | X чел | [H] | минимальная команда |
| Зарплата avg | $X/mo | [F] | [URL для {GEOGRAPHY}] |

*Типы: [F] = факт из research, [B] = benchmark, [H] = гипотеза*

### Модель

| | M1 | M2 | M3 | M6 | M9 | M12 | M18 | M24 |
|---|---|---|---|---|---|---|---|---|
| Total Users | | | | | | | | |
| Paying Users | | | | | | | | |
| **MRR** | | | | | | | | |
| COGS | | | | | | | | |
| **Gross Profit** | | | | | | | | |
| Marketing | | | | | | | | |
| Team | | | | | | | | |
| Infra/Tools | | | | | | | | |
| **Total OpEx** | | | | | | | | |
| **Net P&L** | | | | | | | | |
| **Cash Balance** | | | | | | | | |

## D. RESOLVED CONTRADICTIONS (только DEEP / VERIFIED)

| # | Противоречие | Тип | TRIZ Principle | Решение |
|---|-------------|-----|----------------|---------|
| 1 | [Price: high for economics, low for market] | Physical | Separation in Time | [Freemium → paid after Aha Moment] |
| 2 | [Team: large for speed, small for runway] | Physical | Separation in Space | [Core team + freelancers per project] |
| 3 | [CAC: low for economics, high-quality for LTV] | Technical | #23 Feedback | [Referral loop: low CAC + high-intent users] |

## E. FUNDING ROADMAP

| Раунд | Когда | Сколько | На что | KPIs | Valuation | Confidence |
|-------|-------|---------|--------|------|-----------|:----------:|
| Bootstrap | M0 | $X | MVP | Идея + команда | — | — |
| Pre-seed | M3-6 | $X | PMF validation | X users, X% retention | $X | 0.XX |
| Seed | M9-12 | $X | Scale | $XK MRR, X% growth | $X | 0.XX |
| Series A | M18-24 | $X | Expansion | $XK MRR, proven UE | $X | 0.XX |

## F. BREAK-EVEN

| Сценарий | Платящие | MRR | Месяц | Вероятность |
|----------|---------|-----|:-----:|:-----------:|
| 🟢 Оптимистичный | X | $XK | MX | 20% |
| 🟡 Реалистичный | X | $XK | MX | 60% |
| 🔴 Пессимистичный | X | $XK | MX | 20% |

## G. SENSITIVITY

| Изменение | Break-even | LTV:CAC | Verdict |
|-----------|:----------:|:-------:|---------|
| CAC +50% | +X мес | X:1 | [приемлемо / критично] |
| Churn +2% | +X мес | X:1 | |
| ARPU -20% | +X мес | X:1 | |
| Конверсия -30% | +X мес | — | |

---

## 📈 Confidence Summary

| Блок | Avg Confidence | Min |
|------|:--------------:|:---:|
| Revenue Model | 0.XX | 0.XX |
| Unit Economics | 0.XX | 0.XX |
| P&L Projection | 0.XX | 0.XX |
| Funding Roadmap | 0.XX | 0.XX |
| Break-Even | 0.XX | 0.XX |
| **ИТОГО** | **0.XX** | **0.XX** |

## ⚠️ Рисковые допущения
- [ ] [Допущение с высоким impact и низким confidence]
```

## External Skill References

| Скилл | Режим | Как используется |
|-------|-------|-----------------|
| `goap-research-ed25519` | DEEP | Адаптивный поиск benchmarks + salary data |
| `goap-research-ed25519` | VERIFIED | Верификация финансовых чисел (threshold 0.95 strict) |
| `problem-solver-enhanced` M1 | DEEP | First Principles: деконструкция каждого допущения |
| `problem-solver-enhanced` M6 | DEEP | TRIZ: разрешение pricing / team / CAC противоречий |
| `references/industry-benchmarks.md` | ALL | Справочник unit economics по индустриям |

## Checkpoint 4

```
═══════════════════════════════════════════════════════════════
⏸️ CHECKPOINT 4: Business Model & Finance Complete

💰 LTV:CAC = X:1 | Break-even: Month X
🔧 Противоречий разрешено: X (DEEP/VERIFIED)
📈 Avg Confidence: 0.XX
⚠️ Рисковых допущений: X

Действия:
• "ок"                          → Module 5: Growth Engine
• "пересчитай с [допущениями]"  → новые параметры
• "скорректируй [что]"         → исправить
• "переключи на DEEP/VERIFIED"
• "покажи sensitivity для [X]"

Что выберете?
═══════════════════════════════════════════════════════════════
```
