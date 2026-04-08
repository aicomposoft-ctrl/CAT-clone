# INS-004: Cooldown таймер должен стартовать и на 429, не только на success

**Category:** frontend  
**Status:** Active  
**Hit Count:** 1  
**Date:** 2026-04-06

## Problem

В `useAlertCheck` cooldown таймер (60 сек) запускался только при успешном вызове `/alerts/check`. При получении 429 (Too Many Requests) от API кнопка оставалась активной — пользователь мог нажимать снова и снова, получая 429 каждый раз.

## Solution

Cooldown должен стартовать **и при 429**, и при успехе:

```typescript
// WRONG — cooldown только на success
const mutation = useMutation({
  mutationFn: alertsApi.check,
  onSuccess: () => {
    setCooldownUntil(Date.now() + 60_000)
  },
  onError: (err) => {
    message.error('Ошибка при запуске проверки')  // 429 игнорируется
  }
})

// CORRECT — cooldown и на success, и на 429
const mutation = useMutation({
  mutationFn: alertsApi.check,
  onSuccess: () => {
    setCooldownUntil(Date.now() + 60_000)
    message.success('Проверка запущена')
  },
  onError: (err) => {
    const status = (err as AxiosError).response?.status
    if (status === 429) {
      setCooldownUntil(Date.now() + 60_000)  // ← старт cooldown на 429
      message.warning('Слишком много запросов, подождите 1 минуту')
    } else {
      message.error('Ошибка при запуске проверки')
    }
  }
})
```

## Why It Works

Если API уже вернул 429 — значит лимит исчерпан на стороне сервера. Показывать активную кнопку бессмысленно и вводит пользователя в заблуждение. BDD-сценарий явно требует: "When API returns 429 → Then cooldown timer starts".

## Applies To

- `services/frontend/src/pages/Alerts/hooks/useAlertCheck.ts`
- Любая кнопка с rate-limited действием в проекте
- Общий паттерн: rate-limited actions должны блокировать UI при любом ответе, означающем "лимит исчерпан"
