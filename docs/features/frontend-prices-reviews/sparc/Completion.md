# Completion — Frontend: Prices & Reviews Pages

---

## Pre-Deployment Checklist

- [ ] `tsc --noEmit` passes with zero errors
- [ ] `npm run build` succeeds, no console warnings
- [ ] Prices page: all 4 query calls verified in browser Network tab
- [ ] Reviews page: all 3 query calls verified in browser Network tab
- [ ] Empty state renders when no SKU selected
- [ ] ECharts charts resize correctly when drawer opens
- [ ] Sentiment null → "Pending" tag visible
- [ ] Anomaly direction colors correct (red ↓, green ↑)
- [ ] No placeholder "Sprint 2" text remaining

## Deployment

No backend changes. No DB migrations. Frontend-only:

```bash
# Dev
cd services/frontend && npx vite --port 3000

# Docker
docker compose build frontend
docker compose up -d frontend
```

## Files Changed

```
services/frontend/src/api/prices.ts       ← CREATE
services/frontend/src/api/reviews.ts      ← CREATE
services/frontend/src/pages/Prices/index.tsx   ← REPLACE
services/frontend/src/pages/Reviews/index.tsx  ← REPLACE
```
