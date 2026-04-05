# CAT UI Guide

> The frontend is under active development. This section describes the designed interface based on system technical requirements.

## Interface Structure

### Main Navigation (Left Panel)

```
CAT Dashboard
├── Dashboard      — summary dashboard
├── Content        — content monitoring
├── Stock          — distribution plan vs actual
├── Reviews        — review analytics
├── Prices         — price monitoring
├── Reports        — report export
└── Settings       — system settings
     ├── SKU Management
     ├── Platforms
     ├── Alerts
     └── Users (admin only)
```

**Technologies:**
- React 18 + TypeScript
- Ant Design 5.x (components, theming)
- Apache ECharts 5.x (charts and graphs)
- React Query (server state)
- Zustand (client state)

---

## Key Screens

### Dashboard (Main)

Widgets:
- **Content Score by Platform** — bar chart, top 5 problem SKUs
- **Distribution** — gauge chart, average % across all networks
- **Reviews** — pie chart, positive/negative/neutral over last 7 days
- **Alerts** — cards for recent unhandled alerts
- **Scraping Status** — table: platform / last run / status / SKU count

### Content Score

**Main Table:**
```
[ Filters: Brand | Platform | Date | Score range ]

[ Ant Design Table with server pagination (50 rows/page) ]
Platform | Brand | Article | Name | Content Total | Image | Desc | Comp | URL
  Samokat   Brand   3927   Turkey...   [████ 85%]  91%  79%  87%  [🔗]
  WB        Brand   3927   Turkey...   [███  42%]  35%  50%  44%  [🔗]  ← red

[ Button: Export Content Report ]
```

Click row → **Drawer** opens on the right:
- Side-by-side images: collected vs reference
- Description text diff (green/red highlighting)
- Score history chart (ECharts line, 30 days)

### Stock / Distribution

**Tabs:** By Network | By City | By Address | Assortment Share

**By Network:**
```
[ Filters: Platform | Brand | Week | Distribution threshold ]

Network | Group | SKU | Plan TT | Actual TT | Distribution %
Retailer | Fresh | Chicken wings... | 66 | 66 | [100%] ← green
Retailer | Frozen | Cutlets... | 120 | 87 | [73%] ← red

[ Upload Plan | Export Stock Report ]
```

### Reviews

**Tabs:** Totals by Brand | By Category | Review Texts

**Totals by Brand:**
```
[ Bar chart: brand comparison by positive/negative share ]

Brand | Type | Count | Negative | Neutral | Positive
YourBrand | Client | 1,247 | 22.7% | 15.9% | 61.4%
Competitor | Competitor | 892 | 37.5% | 25.0% | 37.5%
```

**Review Texts** — table with full-text search and color-coded sentiment markers.

### Prices

```
[ Filters: SKU | Platform | Date ]

[ Line chart: price dynamics — your SKU vs competitors ]

Table: SKU | Platform | Price | Discount | Promo | Date
```

### Settings → SKU Management

```
[ Search | Add SKU | Bulk Upload CSV ]

Table: Article | Name | Brand | Platforms | Reference | Status
  3927 | Turkey... | YourBrand | 4 platforms | ✅ uploaded | Active

Click SKU → edit form:
  - SKU fields
  - Reference Image upload (drag & drop)
  - Reference texts (Description, Composition)
  - Platform list (checkboxes)
```

---

## UI Controls

### Score Color Scheme

| Value | Color | Ant Design Token |
|-------|-------|-----------------|
| ≥ 80% | Green | `success` |
| 50–79% | Yellow | `warning` |
| < 50% | Red | `error` |

### Table Pagination

All tables use server-side pagination: 50 rows per page by default. `rowKey` is always the `id` (UUID field), never the array index.

### Notifications

System alerts appear as Ant Design `Notification` toasts in the top right. A notification center is accessible via the bell icon in the header.

### Export Modal

The **Export** button in each section opens an Ant Design `Modal` with options:
- Date range
- Brands / platforms
- Format (xlsx, always)

### Responsive Behavior

The interface is optimized for desktop (1280px+). On mobile devices, main tables fall back to horizontal scroll.
