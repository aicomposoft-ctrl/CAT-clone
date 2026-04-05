# CAT User Guide

## Getting Started

### First Login

1. Go to `https://your-domain.com`
2. Enter the email and password provided by your administrator
3. After login, you will land on the main dashboard

### Changing Your Password

Settings → Profile → Change Password.

---

## Section: Content (Content Monitoring)

### Content Score Table

The main screen shows a table with these columns:

| Column | Description |
|--------|-------------|
| Platform | Marketplace or retailer |
| Brand | Your brand or competitor |
| Article | Product article/SKU code |
| SKU Name | Product name |
| Content Total | Composite score 0–100% |
| Image:Front | Photo match vs reference |
| Description | Description match |
| Composition | Composition/ingredients match |
| URL | Link to the product page |

**Color coding:**
- Green (≥ 80%) — healthy
- Yellow (50–79%) — needs attention
- Red (< 50%) — critical, action required

### How to Read Results

**Content Total** is calculated as:
```
Content Total = 40% × Image Score + 35% × Description Score + 25% × Composition Score
```

The algorithm compares marketplace-collected images and texts against your reference materials using ML embeddings (CLIP for images, multilingual-e5 for text).

### Detailed SKU View

Click any row to open the detail panel:
- Visual comparison: marketplace photo vs reference
- Description diff: differences from reference text highlighted
- 30-day score history chart
- Direct link to the product page

### Filtering and Sorting

- Filters: brand, platform, date range, score range
- Sort by any column — click the header
- To find the most problematic products: sort by **Content Total** ascending

### Exporting the Content Report

1. Click **Export → Content Report**
2. Select date range and brands
3. Download `Content_Report_YYYY-MM-DD.xlsx`

The file contains two sheets:
- **Total** — aggregate score per platform
- **Score card** — detailed table for each SKU × platform

---

## Section: Stock (Distribution)

### Uploading a Distribution Plan

1. Stock section → **Plan Management**
2. Click **Upload Plan**
3. Upload a CSV/Excel file with columns:
   - Platform, Group, Product Name, Target Store Count (plan)
4. Confirmation: "Plan uploaded for N SKUs across M networks"

### Distribution Dashboard

The **By Network** table shows plan vs actual for each retail network:

| Column | Description |
|--------|-------------|
| Platform | Retail network |
| Group | Product group (Fresh, Frozen, etc.) |
| SKU | Product name |
| Plan TT | Target store count |
| Actual TT | Actual stores with product in stock |
| Distribution % | Actual / Plan × 100% |

SKUs with Distribution < 80% are highlighted in red.

### City-Level Drill-Down

Click any SKU → opens a table broken down by city and week (4 weeks history).

### Assortment Share

The **Assortment Share** tab shows your brand's share in the retailer's assortment by city.

### Exporting the Stock Report

**Export → Stock Report** — downloads `Stock_Report_YYYY-MM-DD.xlsx` with 7 sheets:
- Plan vs Actual by Network
- All SKUs by Category/Brand
- SKU by Dark Store & City
- Assortment Share by City
- SKU by Address
- Plan vs Actual Top Cities
- SKU by Store

---

## Section: Reviews

### Overall Analytics

The **Totals by Brand** tab shows sentiment summary across brands:

| Brand | Type | Negative Share | Positive Share |
|-------|------|---------------|----------------|
| Your brand | Client | 22% | 65% |
| Competitor A | Competitor | 38% | 42% |

Sentiment is analyzed by the ruBERT ML model, classifying each review as positive / negative / neutral.

### Review Texts

A filterable list of all reviews with fields:
- Marketplace, Category, Brand, SKU
- Review text, Rating (1–5 stars), Sentiment, Date

Filters: brand, marketplace, category, sentiment, date range.

### Exporting the Reviews Report

**Export → Reviews Report** — Excel with 4 sheets:
- Summary
- Totals by Brand
- Totals by Brand & Category
- Review Texts

---

## Section: Prices

### Price Monitoring

A table with price history per SKU × platform × date. You can compare your price against competitor prices on the same platform.

Promotions and discounts are highlighted.

### Setting Price Alert Thresholds

Settings → Alerts → Add Rule:
- Type: `price_change` or `competitor_promo`
- Threshold: e.g., 10% change
- Email recipients

---

## Section: Settings

### SKU Management

**Settings → SKU Management:**
- Add SKU manually
- Bulk upload via CSV (up to 10,000 rows)
- Upload reference image for each SKU
- Set reference description and composition

### Uploading Reference Materials

1. Settings → SKU → click the article number
2. **Reference materials** section:
   - Image:Front — upload JPG/PNG (reference front photo)
   - Description — paste reference description (up to 5,000 characters)
   - Composition — paste reference composition/ingredients

> After uploading references, the system will automatically recalculate the content score on the next collection cycle (nightly at 02:00).

---

## Frequently Asked Questions

**How often is data updated?**
Content and reviews: daily at 02:00. Prices: every 4 hours.

**Why is the content score low if the product page looks correct?**
Possible reasons: outdated reference (upload a new one), the platform changed its display format. Open the SKU detail view and check the side-by-side comparison.

**How do I get alerted when the score drops?**
Settings → Alerts → create a rule with type `content_drop` and set a threshold (e.g., 70%).

**Can I see other organizations' data?**
No. The system is multi-tenant — each client only sees their own data.

**How many SKUs are supported?**
MVP: up to 10,000 SKUs. v1.0: up to 100,000 SKUs.

**How do I add a new platform?**
Contact your administrator — adding platforms requires the `admin` role.
