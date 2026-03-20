# Few-Shot: CJM Prototype (Noom → НутриМайнд)

> **Это пример для Claude, не для пользователя.**
> Используй как reference при генерации .jsx для ЛЮБОЙ компании.
> Копируй СТРУКТУРУ КОДА, а не контент.

## Пример: как M2 output превращается в 3 варианта

### Input из M2 (Noom case)

```yaml
company: Noom
one_liner: "Weight Watchers + когнитивно-поведенческая психология через AI"
segments:
  - name: "Женщины 30-45, стресс-еда"
    functional_job: "Похудеть без голодания"
    emotional_job: "Чувствовать контроль"
    social_job: "Выглядеть здоровой"
    trigger: "Фото, одежда не подходит, рекомендация врача"
  - name: "Мужчины 35-50, здоровье"
    functional_job: "Снизить вес по медпоказаниям"
    emotional_job: "Не чувствовать стыд"
    trigger: "Анализы, давление, рекомендация врача"
  - name: "Молодёжь 20-30, осознанность"
    functional_job: "Разобраться в отношениях с едой"
    emotional_job: "Быть в гармонии с телом"
    social_job: "Выглядеть осознанным/mindful"
    trigger: "Тренд на mindfulness, подруга посоветовала"
aha_moment: "Персональный план на основе КПТ-профиля"
complaints: ["дорого", "навязчивые уведомления", "коуч отвечает шаблонно"]
positive_patterns: ["психологический подход", "без подсчёта калорий", "уроки короткие"]
pricing: ["Free trial 14 дней", "₽299/мес год", "₽749/мес"]
```

### Генерация 3 вариантов (логика)

```
Axis 1 — AHA:
  A: Персональный план (из M2 aha_moment — основной)
  B: Прогресс за неделю (из complaints — "нет быстрого результата" → покажем через 7 дней)
  C: AI-паттерн (из positive_patterns — "психологический подход" → усилим через AI)

Axis 2 — ENTRY:
  A: Functional Job Segment 1 → "Похудей через психологию"
  B: Emotional Job Segment 3 → "Научись есть осознанно"
  C: Emotional Job Segment 1 → "Разберись почему срываешься"

Axis 3 — PAYWALL:
  A: Сразу после Aha (день 1) → конверсия на wow-эмоции
  B: После 7 дней → привычка сформирована
  C: После первого сокращения срывов → proof of value
```

### Структура .jsx (reference для кода)

```
VARIANTS = {
  A: {
    name, emoji,                    // ID варианта
    col, bg, bgl, bdr, txt,        // Tailwind цвета (подбирать под industry)
    landing: { hl, sub, cta },     // Headline, subheadline, CTA
    onboarding: { q1, q2, style }, // Вопросы из segment triggers
    aha: { title, desc, wow, kpi },// Core value moment
    dash: { hook, lesson, stats }, // Engagement mechanism
    pay: { when, frame },          // Paywall timing + framing
    inv: { hook, mech },           // Referral mechanism
  },
  B: { ... },
  C: { ... },
};

CJM_META = {                       // Стандартная, не меняется
  landing: { stage, aarrr, q },
  onboarding: { ... },
  aha: { ... },
  dash: { ... },
  pay: { ... },
  inv: { ... },
};

// Components (стандартная структура):
// - VariantSwitcher (tabs)
// - ScreenRenderer (6 screens × 3 variants)
// - CJMBadge (overlay toggle)
// - CompareTable (⚖️)
// - Builder (🔧 mix & match)
// - Scoring (🏆)
// - LockedResult (✅)
```

### Чеклист качества генерации

- [ ] Все тексты на языке {GEOGRAPHY} (русский, English, etc.)
- [ ] Headline из JTBD конкретного сегмента, не generic
- [ ] Aha Moment — конкретный, не "вы получите план"
- [ ] Onboarding вопросы из segment triggers (M2)
- [ ] Pricing из M1 реальной компании
- [ ] Dashboard hook разный для каждого варианта
- [ ] Цветовая палитра подобрана под {INDUSTRY}
- [ ] CJM overlay с validation questions для custdev
