# Refinement — Frontend: Prices & Reviews Pages

---

## Edge Cases

| Scenario | Handling |
|----------|----------|
| No SKU selected | `<Empty description="Выберите SKU для просмотра данных" />` — all sections hidden |
| SKU has no price data | API returns empty `items: []` → Table shows Ant Design empty state |
| `sentiment = null` in review | Render `<Tag>Ожидает классификации</Tag>` in gray |
| `cheapest_platform_id = null` | No row highlighted — data insufficient |
| `sentiment_share = null` in stats | Pie chart shows empty state "Sentiment data unavailable" |
| API returns 404 for sku_id | Show Alert error: "SKU not found" — user may have stale selection |
| Date range > 366 days | API returns 422 → show form validation error on DatePicker |
| `change_pct = null` in stats | Stat card shows "—" instead of crash |
| History items from multiple platforms | Group by platform_name for chart series |
| Price is Decimal string "299.00" | Parse with `parseFloat()` for chart, display as-is in table |

---

## Test Cases

```gherkin
Scenario: Prices page - empty state when no SKU
  Given I navigate to /prices
  Then I see SKU selector
  And I see Empty component with "Выберите SKU"
  And no API calls for prices/* are made

Scenario: Prices page - latest table highlights cheapest
  Given skuId is set
  And latest response has cheapest_platform_id = "WB-UUID"
  When table renders
  Then the Wildberries row has class "row-cheapest" with green background

Scenario: Prices page - anomaly direction color
  Given anomaly with direction="down"
  Then change_pct cell renders in red with ↓ icon
  Given anomaly with direction="up"
  Then change_pct cell renders in green with ↑ icon

Scenario: Reviews page - null sentiment tag
  Given review_item.sentiment = null
  Then <Tag> shows "Ожидает" in gray

Scenario: Reviews page - pagination
  Given history.total = 250 and limit = 100
  Then pagination shows 3 pages
  When user clicks page 2
  Then GET /reviews/history?offset=100 is called

Scenario: Reviews page - sentiment filter
  Given sentimentFilter = "negative"
  Then GET /reviews/history?sentiment=negative is called
  And queryKey includes 'negative' to bust cache
```

---

## Performance

- `staleTime: 5 * 60 * 1000` on all queries — avoids refetch on tab switch
- SKU list query: `staleTime: 10 * 60 * 1000` (rarely changes)
- `enabled: !!skuId` — no API calls until SKU selected
- ECharts: `style={{ height: 300 }}` — fixed height prevents layout shift
- History chart: if >500 items, limit to last 90 days by default (API cap)

---

## Accessibility

- SKU Select: `aria-label="Выберите SKU"`
- DatePicker: `aria-label="Период"`
- Anomaly direction: icon + color (not color-only for colorblind users)
- Sentiment tags: use `aria-label="sentiment: positive"`
- Rating: `<Rate disabled value={rating} aria-label={`Rating: ${rating} out of 5`}/>`
