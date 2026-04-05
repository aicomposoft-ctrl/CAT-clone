# Auth Context DI Pattern

**Category:** Pattern
**Maturity:** 🔴 Alpha
**Used in:** CAT (Commerce Analytics Tool)
**Extracted:** 2026-04-05
**Version:** v1.0

---

## When to Use

When a FastAPI application needs to add new context fields (tenant ID, client scope, organization)
to the authentication dependency **without breaking** existing route code that accesses
User attributes directly.

Specifically use when:
- You need to pass `org_id`, `client_id`, or other scope alongside the `User` object
- You have existing routes using `current_user.email`, `current_user.role`, etc.
- You want downstream code to have context without extra DB queries

## When NOT to Use

- Simple single-tenant apps where just returning `User` is sufficient
- When the extra context fields change frequently (prefer explicit parameters then)

## Prerequisites

- FastAPI with Depends()
- SQLAlchemy async session
- JWT-based authentication already working

## Implementation

```python
from dataclasses import dataclass
from typing import Any
from uuid import UUID


@dataclass
class AuthContext:
    """
    Dependency injection payload for authenticated requests.

    Wraps the User ORM object and adds request-scoped context
    (org_id, optional client_id) without requiring extra DB queries.

    The __getattr__ delegation allows existing code written against User
    (ctx.email, ctx.role, ctx.id) to work unchanged after the dependency
    was updated to return AuthContext instead of User.
    """

    user: Any           # ORM User instance — typed as Any to avoid import cycle
    org_id: UUID
    client_id: UUID | None = None

    def __getattr__(self, name: str) -> Any:
        """Delegate unknown attribute access to the wrapped User object."""
        try:
            return getattr(self.user, name)
        except AttributeError:
            raise AttributeError(
                f"'{type(self).__name__}' object has no attribute '{name}'"
            ) from None


# --- FastAPI dependency ---

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> AuthContext:
    """Decode Bearer token, load User, return AuthContext."""
    payload = decode_token(token, expected_type="access")
    user = await UserRepository.get_by_id(db, UUID(payload["sub"]))
    if user is None:
        raise HTTPException(status_code=401, detail="UNAUTHORIZED")

    # Extract optional scope claims from JWT
    client_id = UUID(payload["client_id"]) if payload.get("client_id") else None

    return AuthContext(user=user, org_id=user.org_id, client_id=client_id)


# --- Route usage (backward compatible) ---

@router.get("/me")
async def get_me(ctx: AuthContext = Depends(get_current_user)):
    # Works even for code that only knows about User:
    return {"email": ctx.email, "role": ctx.role, "org_id": ctx.org_id}
```

## Variants

### Variant A: Without delegation (explicit)
If no backward compatibility is needed, skip `__getattr__` and always access `ctx.user.email`.
Safer (explicit), but requires updating all existing routes.

### Variant B: Multiple scope levels
Add additional optional fields like `workspace_id`, `project_id` as `UUID | None`.
Only populate the ones present in the JWT payload.

### Variant C: Shim for compatibility
Keep old `get_user()` dependency returning just `User` (as a shim):
```python
def get_user(ctx: AuthContext = Depends(get_current_user)) -> User:
    return ctx.user
```
Allows incremental migration.

## Gotchas

- `__getattr__` is only called when normal lookup fails, so dataclass fields
  (`user`, `org_id`, `client_id`) are never intercepted — this is correct.
- Do not put mutable defaults in the dataclass (use `None` as default for optionals).
- If User model changes attributes, AuthContext will propagate the change transparently.

## Related Artifacts

- `snippets/jwt-token-type-enforcement.py`
- `patterns/multi-tenant-saas-isolation.md`

## Changelog

- v1.0 (2026-04-05): Initial extraction from CAT multi-client-support feature
