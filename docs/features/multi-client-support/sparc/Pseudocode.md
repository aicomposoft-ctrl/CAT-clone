# Pseudocode — Multi-Client Support

> **Feature:** multi-client-support | **Phase:** SPARC Pseudocode | **Date:** 2026-04-04

---

## Data Structures

### Client (DB model)
```
type Client = {
    id:            UUID
    org_id:        UUID
    name:          str (max 255)
    slug:          str (max 100, unique per org)
    contact_email: str | None
    logo_url:      str | None
    is_active:     bool = True
    created_at:    datetime
    updated_at:    datetime
}
```

### AuthContext (new — replaces bare User in deps)
```
type AuthContext = {
    user:      User
    org_id:    UUID          # from user.org_id
    client_id: UUID | None   # from JWT claim, None = all-clients mode
}
```

### ClientCreateRequest
```
type ClientCreateRequest = {
    name:          str (1..255)
    slug:          str (1..100, pattern: ^[a-z0-9-]+$)
    contact_email: EmailStr | None = None
    logo_url:      HttpUrl | None = None
}
```

### ClientResponse
```
type ClientResponse = {
    id:            UUID
    name:          str
    slug:          str
    contact_email: str | None
    logo_url:      str | None
    is_active:     bool
    brand_count:   int
    created_at:    datetime
}
```

### SwitchClientRequest
```
type SwitchClientRequest = {
    client_id: UUID | None   # None = switch to all-clients mode
}
```

---

## Core Algorithms

### Algorithm: Client Context Injection (updated get_current_user)

```
FUNCTION get_current_user(token: str, db: AsyncSession) -> AuthContext:

    # Existing JWT decode (unchanged)
    payload = decode_token(token, expected_type="access")
    user_id = UUID(payload["sub"])
    user = await UserRepository.get_by_id(db, user_id)
    IF user is None: RAISE 401

    # NEW: extract optional client_id claim
    raw_client_id = payload.get("client_id")  # may be absent
    client_id: UUID | None = UUID(raw_client_id) if raw_client_id else None

    # NEW: validate client belongs to user's org (prevent claim forgery)
    IF client_id is not None:
        client = await ClientRepository.get_active_by_id_and_org(
            db, client_id, user.org_id
        )
        IF client is None:
            RAISE 401 "INVALID_CLIENT_CONTEXT"
            # Note: 401 not 403 — forged token should look like auth failure

    RETURN AuthContext(user=user, org_id=user.org_id, client_id=client_id)
```

---

### Algorithm: Switch Client Context

```
FUNCTION switch_client_context(
    request: SwitchClientRequest,
    ctx: AuthContext,
    db: AsyncSession
) -> TokenResponse:

    IF request.client_id is not None:
        # Validate client exists, is active, and belongs to user's org
        client = await ClientRepository.get_active_by_id_and_org(
            db, request.client_id, ctx.org_id
        )
        IF client is None:
            # Distinguish "wrong org" from "inactive" — both return same error
            # to prevent enumeration
            RAISE 403 "CLIENT_NOT_IN_ORG"

    # Issue new access token with updated client_id claim
    # Fresh 15-minute window (do not inherit original token's exp)
    new_token = create_access_token(
        user_id   = ctx.user.id,
        org_id    = ctx.org_id,
        role      = ctx.user.role,
        client_id = request.client_id,   # None = clear context
    )

    RETURN TokenResponse(access_token=new_token, token_type="bearer")
```

---

### Algorithm: Client-Scoped Brand Query

```
FUNCTION get_brands(
    db: AsyncSession,
    ctx: AuthContext,
    brand_type: str | None = None
) -> list[Brand]:

    query = select(Brand).where(Brand.org_id == ctx.org_id)

    IF ctx.client_id is not None:
        query = query.where(Brand.client_id == ctx.client_id)
    # If client_id is None → all-clients mode, no client filter applied

    IF brand_type is not None:
        query = query.where(Brand.type == brand_type)

    result = await db.execute(query.order_by(Brand.name))
    RETURN result.scalars().all()
```

Pattern for all other repos: same `IF ctx.client_id is not None` guard added to every list query.

---

### Algorithm: Create Client

```
FUNCTION create_client(
    db: AsyncSession,
    request: ClientCreateRequest,
    ctx: AuthContext        # user must be admin — enforced by require_role in router
) -> ClientResponse:

    # Check slug uniqueness within org
    existing = await ClientRepository.get_by_slug_and_org(
        db, request.slug, ctx.org_id
    )
    IF existing is not None:
        RAISE 409 "SLUG_CONFLICT"

    client = Client(
        org_id        = ctx.org_id,
        name          = request.name,
        slug          = request.slug,
        contact_email = request.contact_email,
        logo_url      = request.logo_url,
    )
    await db.add(client)
    await db.commit()

    brand_count = 0  # new client has no brands yet
    RETURN ClientResponse.from_orm(client, brand_count=brand_count)
```

---

### Algorithm: Assign Brand to Client

```
FUNCTION assign_brand_to_client(
    db: AsyncSession,
    brand_id: UUID,
    client_id: UUID | None,
    ctx: AuthContext
) -> Brand:

    brand = await BrandRepository.get_by_id_and_org(db, brand_id, ctx.org_id)
    IF brand is None:
        RAISE 404 "BRAND_NOT_FOUND"

    IF client_id is not None:
        client = await ClientRepository.get_active_by_id_and_org(
            db, client_id, ctx.org_id
        )
        IF client is None:
            RAISE 403 "CLIENT_NOT_IN_ORG"

    brand.client_id = client_id   # None = unassign
    await db.commit()
    RETURN brand
```

---

## API Contracts

### POST /api/v1/clients
```
Request:
    Headers: { Authorization: Bearer <jwt> }
    Body: { "name": "Nestle RU", "slug": "nestle-ru", "contact_email": "contact@nestle.ru" }

Response (201):
    { "id": "uuid", "name": "Nestle RU", "slug": "nestle-ru",
      "contact_email": "contact@nestle.ru", "logo_url": null,
      "is_active": true, "brand_count": 0, "created_at": "..." }

Response (409): { "detail": "SLUG_CONFLICT" }
Response (403): { "detail": "INSUFFICIENT_PERMISSIONS" }
```

### POST /api/v1/auth/switch-client
```
Request:
    Headers: { Authorization: Bearer <jwt> }
    Body: { "client_id": "uuid" }   or   { "client_id": null }

Response (200):
    { "access_token": "new.jwt.token", "token_type": "bearer" }

Response (403): { "detail": "CLIENT_NOT_IN_ORG" }
```

### GET /api/v1/clients
```
Response (200):
    {
        "items": [
            { "id": "uuid", "name": "Nestle RU", "slug": "nestle-ru",
              "brand_count": 5, "is_active": true, "created_at": "..." }
        ],
        "total": 1
    }
```

### PATCH /api/v1/brands/{id}
```
Request body (partial update):
    { "client_id": "uuid" }   or   { "client_id": null }

Response (200): updated Brand object with client_id field
Response (403): { "detail": "CLIENT_NOT_IN_ORG" }
```

---

## Error Handling

| Error | HTTP | Detail Code | When |
|-------|------|-------------|------|
| Slug already exists in org | 409 | SLUG_CONFLICT | POST /clients |
| Client not in user's org | 403 | CLIENT_NOT_IN_ORG | switch-client, brand assign |
| Invalid client in JWT | 401 | INVALID_CLIENT_CONTEXT | Any request with forged claim |
| Client not found / inactive | 404 | CLIENT_NOT_FOUND | GET /clients/{id} |
| Viewer creating client | 403 | INSUFFICIENT_PERMISSIONS | role check |
