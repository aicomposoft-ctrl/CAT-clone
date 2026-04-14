# Security Rules — CAT

## Multi-Tenant Isolation (CRITICAL)

Every database query MUST be scoped to `org_id`. No exceptions.

```python
# CORRECT: always filter by org_id
skus = db.query(SKU).filter(SKU.org_id == current_user.org_id).all()

# WRONG: missing tenant scope — SECURITY BUG
skus = db.query(SKU).all()
```

PostgreSQL Row-Level Security (RLS) is the last line of defense. Application-level filtering is mandatory.

## Authentication

- JWT access tokens: 15 minutes expiry
- Refresh tokens: 7 days
- `JWT_SECRET` must be validated at startup — missing = `sys.exit(1)`
- No fallback defaults: `JWT_SECRET = os.environ["JWT_SECRET"]` not `.get("JWT_SECRET", "default")`
- Passwords: bcrypt hashing via passlib, minimum cost factor 12
- Account lockout: after 5 failed attempts, lock for 15 minutes

## Authorization (RBAC)

| Role | Can |
|------|-----|
| admin | Everything + user management + billing |
| manager | CRUD SKUs, view all data, export, configure alerts |
| viewer | Read-only, export only |

Always check role in route handlers:
```python
@router.delete("/skus/{id}")
async def delete_sku(id: UUID, user: User = Depends(get_current_user)):
    require_role(user, ["admin", "manager"])  # never skip this
```

## Rate Limiting

- Auth endpoints (`/api/v1/auth/login`, `/api/v1/auth/refresh`): 10 req/min per IP
- Export endpoints: 5 req/min per org (large file generation)
- General API: 100 req/min per user

## Input Validation

- All user inputs validated via Pydantic models — never trust raw request data
- File uploads: validate MIME type + magic bytes (not just extension)
- CSV imports: limit to 10,000 rows, validate each row schema before processing
- URL inputs: validate against allowlist of known platform URL patterns

## S3 / MinIO Storage

- Reference images: private access only. No public S3 URLs.
- Presigned URLs for display: expiry 1 hour maximum
- Never store S3 credentials in code — use `MINIO_ACCESS_KEY` and `MINIO_SECRET_KEY` env vars
- Bucket names must not be guessable (use UUID suffix)

## External APIs / Scraping

- Proxy credentials stored in environment variables, never in code
- `BaseScraper.rate_limit` must be respected — never remove rate limiting
- User-agent rotation mandatory for all scrapers
- Scraped data is untrusted: sanitize all text before storing (strip HTML, limit lengths)

## Secrets Management

See `.claude/rules/secrets-management.md` for full protocol.

Required at startup validation:
```python
REQUIRED_SECRETS = ["JWT_SECRET", "POSTGRES_URL", "MINIO_ACCESS_KEY", "MINIO_SECRET_KEY", "SMTP_PASSWORD"]
for secret in REQUIRED_SECRETS:
    if not os.environ.get(secret):
        logger.critical(f"Missing required secret: {secret}")
        sys.exit(1)
```

## HTTPS

- All traffic through Nginx with SSL termination
- HTTP → HTTPS redirect mandatory in production
- HSTS header: `Strict-Transport-Security: max-age=31536000`

## Security Headers (Nginx)

```nginx
add_header X-Content-Type-Options nosniff;
add_header X-Frame-Options DENY;
add_header X-XSS-Protection "1; mode=block";
add_header Content-Security-Policy "default-src 'self'";
```

## OWASP Checklist (code review must verify)

- [ ] A01: All queries tenant-scoped
- [ ] A02: No weak JWT secrets, no hardcoded credentials
- [ ] A03: No SQL via string interpolation — use SQLAlchemy ORM or parameterized queries
- [ ] A04: Rate limiting on all public endpoints
- [ ] A05: Security headers present
- [ ] A07: Account lockout implemented
- [ ] A09: Auth events logged (login, logout, failed attempts)
