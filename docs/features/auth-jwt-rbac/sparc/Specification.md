# Feature Specification: Auth (JWT + RBAC)

**Feature ID:** auth-jwt-rbac
**Last Updated:** 2026-03-27

---

## 1. User Stories

### US-A01: Login

```
As a CAT user (any role),
I want to log in with my email and password,
So that I receive a JWT token to access the platform.

Acceptance Criteria:
Given I have a valid account with role "manager"
When I POST /api/v1/auth/login with correct email and password
Then I receive HTTP 200 with access_token, refresh_token, token_type, expires_in, and user info

Given I POST /api/v1/auth/login with wrong password
Then I receive HTTP 401 with detail "INVALID_CREDENTIALS"

Given my account is locked (5 failed attempts)
When I POST /api/v1/auth/login with correct password
Then I receive HTTP 423 with detail "ACCOUNT_LOCKED" and lockout_until timestamp
```

### US-A02: Token Refresh

```
As a logged-in user,
I want my session to auto-renew without re-entering credentials,
So that I'm not kicked out every 15 minutes.

Acceptance Criteria:
Given I have a valid refresh token (not expired, not revoked)
When I POST /api/v1/auth/refresh with the refresh token
Then I receive a new access_token (new 15 min window)
And the refresh token remains valid until its original 7-day expiry

Given I POST /api/v1/auth/refresh with an expired or invalid refresh token
Then I receive HTTP 401 with detail "INVALID_REFRESH_TOKEN"
```

### US-A03: Logout

```
As a logged-in user,
I want to log out explicitly,
So that my refresh token is invalidated and cannot be reused.

Acceptance Criteria:
Given I have a valid access token
When I POST /api/v1/auth/logout
Then I receive HTTP 200
And the current refresh token is revoked
And subsequent refresh attempts with that token return 401
```

### US-A04: Get Current User

```
As a frontend application,
I want to get current user info on page load,
So that I can initialize the session and show the right UI for the user's role.

Acceptance Criteria:
Given a valid Bearer token
When I GET /api/v1/auth/me
Then I receive user id, email, role, org_id, org_name

Given no token or expired token
When I GET /api/v1/auth/me
Then I receive HTTP 401
```

### US-A05: RBAC Enforcement

```
As a viewer-role user,
I want mutation endpoints to reject my requests,
So that I cannot accidentally or intentionally modify data.

Acceptance Criteria:
Given I am authenticated as "viewer"
When I attempt DELETE /api/v1/skus/{id}
Then I receive HTTP 403 with detail "INSUFFICIENT_PERMISSIONS"

Given I am authenticated as "manager"
When I attempt DELETE /api/v1/skus/{id} for an SKU in my org
Then I receive HTTP 200 (deletion proceeds)

Given I am authenticated as "manager"
When I attempt GET /api/v1/admin/users
Then I receive HTTP 403 (admin-only endpoint)
```

### US-A06: Account Lockout

```
As a security measure,
I want accounts to lock after repeated failed login attempts,
So that brute-force attacks are mitigated.

Acceptance Criteria:
Given a user has made 4 failed login attempts
When they make a 5th failed attempt
Then the account locks for 15 minutes
And HTTP 423 is returned with lockout_until

Given an account is locked
When 15 minutes pass
Then the account unlocks automatically
And the next valid login succeeds
```

---

## 2. API Specification

### POST /api/v1/auth/login

```
Request:
  Content-Type: application/json
  Body: {
    "email": "manager@brand.ru",
    "password": "S3cur3P@ss!"
  }

Response 200:
  {
    "access_token": "eyJhbGciOiJIUzI1NiJ9...",
    "refresh_token": "eyJhbGciOiJIUzI1NiJ9...",
    "token_type": "Bearer",
    "expires_in": 900,
    "user": {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "email": "manager@brand.ru",
      "role": "manager",
      "org_id": "660e8400-e29b-41d4-a716-446655440001",
      "org_name": "ИндиЛайт"
    }
  }

Response 401: { "detail": "INVALID_CREDENTIALS" }
Response 422: { "detail": [{ "loc": ["body", "email"], "msg": "value is not a valid email" }] }
Response 423: { "detail": "ACCOUNT_LOCKED", "lockout_until": "2026-03-27T14:45:00Z" }
Response 429: { "detail": "TOO_MANY_REQUESTS" }
```

### POST /api/v1/auth/refresh

```
Request:
  Content-Type: application/json
  Body: { "refresh_token": "eyJhbGciOiJIUzI1NiJ9..." }

Response 200: { "access_token": "eyJhbGciOiJIUzI1NiJ9...", "expires_in": 900 }
Response 401: { "detail": "INVALID_REFRESH_TOKEN" }
```

### POST /api/v1/auth/logout

```
Request:
  Headers: { Authorization: Bearer <access_token> }
  Body: { "refresh_token": "eyJhbGciOiJIUzI1NiJ9..." }

Response 200: { "message": "Logged out successfully" }
Response 401: { "detail": "UNAUTHORIZED" }
```

### GET /api/v1/auth/me

```
Request:
  Headers: { Authorization: Bearer <access_token> }

Response 200:
  {
    "id": "uuid",
    "email": "manager@brand.ru",
    "role": "manager",
    "org_id": "uuid",
    "org_name": "ИндиЛайт"
  }

Response 401: { "detail": "UNAUTHORIZED" }
```

---

## 3. BDD Scenarios (Gherkin)

```gherkin
Feature: Authentication and Authorization

  Background:
    Given the database contains organization "ИндиЛайт" with id "org-001"
    And user "manager@brand.ru" with role "manager" and bcrypt password hash

  Scenario: Successful login
    When I POST /api/v1/auth/login with {"email": "manager@brand.ru", "password": "correct"}
    Then response status is 200
    And response contains "access_token"
    And response contains "refresh_token"
    And response.user.role equals "manager"
    And response.user.org_id equals "org-001"

  Scenario: Invalid credentials
    When I POST /api/v1/auth/login with {"email": "manager@brand.ru", "password": "wrong"}
    Then response status is 401
    And response.detail equals "INVALID_CREDENTIALS"

  Scenario: Account lockout after 5 failed attempts
    When I POST /api/v1/auth/login with wrong password 5 times
    Then response status is 423
    And response.detail equals "ACCOUNT_LOCKED"
    And response contains "lockout_until"

  Scenario: Successful token refresh
    Given I have a valid refresh_token from login
    When I POST /api/v1/auth/refresh with that refresh_token
    Then response status is 200
    And response contains new "access_token"

  Scenario: Expired refresh token rejected
    Given I have a refresh_token that expired 1 day ago
    When I POST /api/v1/auth/refresh with that refresh_token
    Then response status is 401

  Scenario: Viewer cannot delete SKU
    Given I am authenticated as viewer "viewer@brand.ru"
    When I DELETE /api/v1/skus/sku-001
    Then response status is 403

  Scenario: Manager can delete own org's SKU
    Given I am authenticated as manager "manager@brand.ru" in org "org-001"
    And SKU "sku-001" belongs to org "org-001"
    When I DELETE /api/v1/skus/sku-001
    Then response status is 200

  Scenario: Cross-org isolation — manager cannot delete other org's SKU
    Given I am authenticated as manager "manager@brand.ru" in org "org-001"
    And SKU "sku-999" belongs to org "org-002"
    When I DELETE /api/v1/skus/sku-999
    Then response status is 404
    And response.detail equals "SKU not found"

  Scenario: Unauthenticated request rejected
    Given no Authorization header is provided
    When I GET /api/v1/auth/me
    Then response status is 401

  Scenario: Explicit logout revokes refresh token
    Given I am logged in and have valid access_token and refresh_token
    When I POST /api/v1/auth/logout with the refresh_token
    Then response status is 200
    And response.message equals "Logged out successfully"
    When I POST /api/v1/auth/refresh with the same refresh_token
    Then response status is 401
    And response.detail equals "INVALID_REFRESH_TOKEN"

  Scenario: Invalid email format returns 422
    When I POST /api/v1/auth/login with {"email": "not-an-email", "password": "password123"}
    Then response status is 422
    And response.detail contains validation error for "email" field

  Scenario: Rate limit exceeded on login returns 429
    When I POST /api/v1/auth/login more than 10 times within 60 seconds from same IP
    Then response status is 429
    And response.detail equals "TOO_MANY_REQUESTS"

  Scenario: Login with nonexistent email returns same error as wrong password
    When I POST /api/v1/auth/login with {"email": "nobody@fake.com", "password": "anything"}
    Then response status is 401
    And response.detail equals "INVALID_CREDENTIALS"
    # Note: same response as wrong password — prevents user enumeration via timing

  Scenario: Token refresh does not rotate the refresh token (multi-use until expiry)
    Given I have a valid refresh_token
    When I POST /api/v1/auth/refresh with that refresh_token
    Then response status is 200
    And I can POST /api/v1/auth/refresh again with the SAME refresh_token
    And response status is 200
    # Refresh token is NOT rotated — remains valid until 7-day expiry or explicit logout
```

---

## 4. Refresh Token Storage

Refresh tokens are stored in PostgreSQL for revocation support:

```sql
CREATE TABLE refresh_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash VARCHAR(64) NOT NULL UNIQUE,  -- SHA256 of the token
    expires_at TIMESTAMPTZ NOT NULL,
    revoked BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_refresh_tokens_user_id ON refresh_tokens(user_id);
CREATE INDEX idx_refresh_tokens_token_hash ON refresh_tokens(token_hash);
```
