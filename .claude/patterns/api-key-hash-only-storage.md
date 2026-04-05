# API Key: Hash-Only Storage Pattern

**Category:** Pattern
**Maturity:** 🔴 Alpha
**Used in:** CAT (Commerce Analytics Tool)
**Extracted:** 2026-04-05
**Version:** v1.0

---

## When to Use

When implementing API key authentication for any service where:
- Keys are long-lived credentials (unlike JWT access tokens)
- A DB breach must not yield usable keys
- Users need a recognizable prefix for key management (identifying which key is which)
- The full key must only be shown once (at creation time)

Standard pattern for: public APIs, CI/CD tokens, SDK integrations, webhook secrets.

## When NOT to Use

- Short-lived session tokens (use JWT instead)
- Internal service-to-service auth (use mTLS or service accounts)
- When key rotation needs to be atomic (this pattern requires delete+create)

## Prerequisites

- Any relational DB (PostgreSQL, MySQL, SQLite)
- `secrets` module (Python stdlib) or equivalent CSPRNG
- `hashlib.sha256` (Python stdlib)

## Implementation

```python
import hashlib
import secrets
from uuid import UUID


def generate_api_key(env: str = "live") -> tuple[str, str, str]:
    """
    Generate an API key tuple.

    Returns:
        (full_key, key_prefix, key_hash)

        full_key:   {prefix}_{env}_{random}  — shown to user ONCE, never stored
        key_prefix: first 8 chars of random  — stored for display in UI
        key_hash:   SHA-256(full_key)         — the ONLY value stored in DB
    """
    raw = secrets.token_urlsafe(30)          # 40 random URL-safe chars
    full_key = f"{PREFIX}_{env}_{raw}"       # e.g. "myapp_live_xK9mN2..."
    key_prefix = raw[:8]                     # display-only, not secret
    key_hash = hashlib.sha256(full_key.encode()).hexdigest()
    return full_key, key_prefix, key_hash


# --- DB model (store only hash + prefix, never full key) ---

class APIKey(Base):
    __tablename__ = "api_keys"

    id = Column(UUID, primary_key=True, default=uuid4)
    org_id = Column(UUID, ForeignKey("organizations.id"), nullable=False)
    name = Column(String(255), nullable=False)      # human label
    key_prefix = Column(String(8), nullable=False)  # display only
    key_hash = Column(String(64), nullable=False, unique=True)  # SHA-256
    revoked = Column(Boolean, default=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=func.now())


# --- Validation (lookup by hash, never by raw key) ---

async def validate_api_key(raw_key: str, db: AsyncSession) -> APIKey | None:
    """Look up API key by its SHA-256 hash."""
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    result = await db.execute(
        select(APIKey)
        .where(APIKey.key_hash == key_hash)
        .where(APIKey.revoked == False)  # noqa: E712
    )
    return result.scalar_one_or_none()


# --- Creation response: return full key ONCE ---

class APIKeyCreateResponse(BaseModel):
    id: UUID
    name: str
    key: str          # full plaintext key — returned ONCE, not stored
    key_prefix: str   # stored — for display in management UI
    expires_at: datetime | None
    created_at: datetime
```

## Key Format Convention

```
{APP_PREFIX}_{env}_{random}

Examples:
  myapp_live_xK9mN2abcdefghijklmno...   # production key
  myapp_test_abcdefghijklmnopqrstu...   # test/sandbox key
```

Benefits of typed prefix:
- Easy to grep in logs/code
- Distinguish live vs. test keys at a glance
- GitHub/GitLab can auto-scan for leaked keys if format is registered

## Variants

### Variant A: With key scope
Add a `scopes` JSON column to restrict what the key can access:
```python
scopes = Column(JSON, default=["read"])  # ["read", "write", "admin"]
```

### Variant B: Rate-limiting by hash prefix
For rate limiting, use first 16 chars of the hash as the Redis key:
```python
rate_key = f"rate:apikey:{key_hash[:16]}"
```
**Never** use `key_prefix` for rate limiting — 8 chars is insufficient collision space.

### Variant C: Opaque tokens (no prefix structure)
For maximum simplicity, skip the env prefix:
```python
full_key = secrets.token_urlsafe(40)
```

## Gotchas

- **Never log the full raw key.** Use `key_prefix` in log lines only.
- The display prefix (8 chars) is NOT a secret — it's safe to store and display.
- `key_hash[:16]` for rate limiting buckets is fine; `key_prefix` is NOT (collision risk).
- Revocation is soft-delete. For hard-delete, ensure no race between validation and delete.
- `secrets.token_urlsafe(30)` gives ~200 bits of entropy — sufficient for brute-force resistance.

## Related Artifacts

- `snippets/jwt-token-type-enforcement.py`
- `rules/anti-enumeration-404.md`

## Changelog

- v1.0 (2026-04-05): Initial extraction from CAT API Keys feature (api_keys domain)
