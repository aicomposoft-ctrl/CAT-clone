# CAT User & Admin Flows

## User Flow: Registration and First Login

```mermaid
sequenceDiagram
    actor Admin as Administrator
    actor User as Trade Marketing Manager
    participant API as CAT API
    participant Email as Email

    Admin->>API: POST /auth/users {email, role: manager}
    API->>Email: Send invite with temporary password
    Email-->>User: Invitation email with link and password
    User->>API: POST /auth/login {email, temp_password}
    API-->>User: JWT access_token + refresh_token
    User->>API: POST /auth/change-password
    API-->>User: 200 OK — password changed
    User->>API: GET /content/scores (first data request)
```

**Steps:**
1. Administrator creates an account via Settings → Users
2. User receives an email with a temporary password
3. First login → change password → access dashboard

---

## User Flow: Add SKU and Upload Reference

```mermaid
sequenceDiagram
    actor BM as Brand Manager
    participant UI as CAT Dashboard
    participant API as CAT API
    participant S3 as MinIO S3

    BM->>UI: Settings → SKU Management → Add SKU
    UI->>API: POST /skus {brand, article, name, barcode, platforms}
    API-->>UI: SKU created {id, status: active}
    BM->>UI: Upload reference image (drag & drop)
    UI->>API: POST /skus/{id}/reference {image_file}
    API->>S3: Store image (private bucket)
    S3-->>API: S3 URL
    API->>API: Compute CLIP embedding, cache in Redis
    API-->>UI: Reference uploaded ✅
    BM->>UI: Paste reference description and composition
    UI->>API: PUT /skus/{id} {reference_description, reference_composition}
    API-->>UI: Updated ✅
    UI-->>BM: "Next recalculation: tonight at 02:00"
```

**What happens under the hood:**
- CLIP embedding of the reference image is cached immediately
- multilingual-e5 text embedding is cached immediately
- Content score will be recalculated in the next nightly cycle (02:00)

---

## User Flow: Daily Content Monitoring

```mermaid
sequenceDiagram
    actor TM as Trade Marketing Manager
    participant UI as CAT Dashboard
    participant API as CAT API
    participant Email as Email

    Note over API: 02:00 — automatic data collection
    API->>API: Celery Beat → collect_content_all_skus()
    API->>API: Processor → calculate content scores
    API->>API: Alerter → check alert thresholds
    API->>Email: Send alerts (if score < threshold)
    Email-->>TM: "⚠️ Content score dropped: SKU 3927 on WB — 42%"

    TM->>UI: Open Content section
    UI->>API: GET /content/scores?sort=content_total&order=asc
    API-->>UI: SKU list sorted by score ascending
    TM->>UI: Click SKU with low score
    UI->>API: GET /content/scores/{sku_id}/history
    API-->>UI: Detailed comparison + 30-day history
    TM->>TM: Decide whether to correct the product card
```

---

## User Flow: Export Content Report for Client

```mermaid
sequenceDiagram
    actor AM as Agency Manager
    participant UI as CAT Dashboard
    participant API as CAT API
    participant Excel as Excel File

    AM->>UI: Reports → Content Report
    UI-->>AM: Form: select period, brands
    AM->>UI: Select "Mar 10–17, 2025", brand "YourBrand"
    UI->>API: GET /reports/content?date_from=2025-03-10&date_to=2025-03-17
    API->>API: openpyxl → generate Excel using client template
    API-->>UI: Streaming response (.xlsx)
    UI-->>AM: Content_Report_2025-03-17.xlsx (download)
    AM->>AM: Send report to client
```

---

## User Flow: Check Distribution Plan vs Actual

```mermaid
sequenceDiagram
    actor TM as Trade Marketing Manager
    participant UI as CAT Dashboard
    participant API as CAT API

    TM->>UI: Stock → Upload Plan
    UI->>API: POST /stock/plan (CSV/Excel file)
    API->>API: Parse, store plan per SKU × network
    API-->>UI: "Plan uploaded for 45 SKUs across 3 networks"

    Note over API: Nightly data collection
    API->>API: collect_stock_all_skus() → update actual store count

    TM->>UI: Stock → Distribution → By Network
    UI->>API: GET /stock/distribution?network=Retailer
    API-->>UI: Plan vs actual table with distribution %
    TM->>UI: Click SKU with Distribution < 80%
    UI->>API: GET /stock/by-city?sku_id=...
    API-->>UI: City breakdown, 4 weeks
    TM->>TM: Escalate to logistics for specific cities
```

---

## Admin Flow: Initial System Setup

```mermaid
sequenceDiagram
    actor Admin as System Admin
    participant Server as VPS Server
    participant Docker as Docker Compose
    participant API as CAT API

    Admin->>Server: ssh user@vps && git clone
    Admin->>Server: cp .env.example .env && nano .env
    Admin->>Docker: docker compose up -d postgres redis minio clickhouse
    Admin->>Docker: docker compose run --rm api alembic upgrade head
    Admin->>Docker: docker compose up -d api collector processor beat frontend nginx
    Admin->>API: curl /api/v1/health → {status: ok}

    Admin->>API: POST /auth/users {email: admin@org.com, role: admin}
    Admin->>API: POST /platforms (add WB, Ozon, Samokat, Lenta)
    Admin->>API: POST /auth/users (create accounts for managers)
    Note over Admin: System is ready for use
```

---

## Admin Flow: User Management

```mermaid
sequenceDiagram
    actor Admin as Admin
    participant UI as CAT Dashboard
    participant API as CAT API

    Admin->>UI: Settings → Users → Add User
    UI->>API: POST /auth/users {email, role: manager, org_id}
    API-->>UI: User created, invite sent

    Note over Admin: User no longer works at the company
    Admin->>UI: Settings → Users → Deactivate User
    UI->>API: PUT /auth/users/{id} {is_active: false}
    API->>API: Invalidate all refresh tokens for user
    API-->>UI: User deactivated ✅
```

---

## Admin Flow: System Health Monitoring

```mermaid
sequenceDiagram
    actor Admin as Admin / DevOps
    participant Flower as Flower UI
    participant Grafana as Grafana
    participant API as CAT API
    participant Telegram as Telegram Bot

    Note over API: 02:00 — scheduled data collection
    API->>Flower: Tasks launched (collect × 1247 SKUs)

    Note over API: 04:15 — issue detected: WB scraper 30% errors
    API->>Telegram: ⚠️ "WB scraper success rate: 70% (threshold 80%)"
    Admin->>Flower: Check failed tasks for WB
    Admin->>API: Restart stuck tasks

    Admin->>Grafana: Open metrics dashboard
    Grafana-->>Admin: API latency, DB connections, Redis memory

    Admin->>API: GET /api/v1/health → all checks: ok
    Admin->>Admin: Incident resolved, log it
```
