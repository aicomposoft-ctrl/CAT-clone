# INS-003: React Query v5 — нет onSuccess в useQuery, использовать useEffect

**Category:** frontend  
**Status:** Active  
**Hit Count:** 1  
**Date:** 2026-04-06

## Problem

После обновления на React Query v5 (`@tanstack/react-query@^5`) код с `onSuccess` в `useQuery` перестал компилироваться:

```typescript
// WRONG — v5 удалил onSuccess из useQuery
const { data } = useQuery({
  queryKey: ['configs'],
  queryFn: fetchConfigs,
  onSuccess: (data) => {  // ❌ TypeScript error: Object literal may only specify known properties
    setLocalState(data)
  }
})
```

## Solution

В v5 `onSuccess`/`onError`/`onSettled` удалены из `useQuery`. Использовать `useEffect`:

```typescript
// CORRECT — v5 паттерн
const { data } = useQuery({
  queryKey: ['configs'],
  queryFn: fetchConfigs,
})

useEffect(() => {
  if (data) {
    setLocalState(data)
  }
}, [data])
```

Для side-effects при мутациях — `onSuccess` в `useMutation` **остался** и работает нормально:

```typescript
const mutation = useMutation({
  mutationFn: createConfig,
  onSuccess: () => {           // ✅ работает в useMutation
    queryClient.invalidateQueries({ queryKey: ['configs'] })
  }
})
```

## Why It Works

React Query v5 убрал колбэки из `useQuery` намеренно — они вызывали проблемы с StrictMode и двойным рендером. `useEffect` — официально рекомендованная замена.

## Applies To

- `services/frontend/src/pages/Alerts/hooks/useAlertConfigs.ts`
- Все хуки с `useQuery` в проекте
- При апгрейде с v4 → v5: глобальный поиск `useQuery.*onSuccess`
