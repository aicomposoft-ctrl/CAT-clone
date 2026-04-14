"""
Timing Attack Mitigation: Dummy Hash for Login
===============================================

Pattern: Pre-compute a real bcrypt hash at module load time.
When a login attempt uses a non-existent email, run bcrypt.verify() against
the dummy hash instead of returning immediately. This burns ~250ms regardless
of whether the user exists, preventing timing-based user enumeration.

When to use:
  - Any login endpoint that looks up users by email before verifying password
  - Anywhere timing differences could reveal whether an account exists

When NOT to use:
  - Rate-limited endpoints with lockout (lockout already prevents enumeration)
  - Non-password auth flows (OAuth, magic links)

Prerequisites: passlib[bcrypt]

The key insight:
  BAD:  if user not found → return 401 immediately (takes <1ms, leaks user existence)
  GOOD: if user not found → verify("dummy", dummy_hash) then return 401 (takes ~250ms,
        indistinguishable from wrong-password for existing user)

Maturity: 🔴 Alpha
Source: CAT (core/security.py), 2026-04-05
"""

from passlib.context import CryptContext

_pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=12,    # hardcode cost — do NOT read from config (weakening risk)
)

# Computed ONCE at module load with the real bcrypt cost=12.
# verify("dummy", _DUMMY_HASH) takes the same ~250ms as verifying a real user.
# A trivially crafted fake string would return in microseconds and leak timing data.
_DUMMY_TIMING_GUARD_HASH: str = _pwd_context.hash("_dummy_timing_guard_")


def get_timing_dummy_hash() -> str:
    """
    Return the pre-computed dummy hash for timing attack prevention.

    Usage in authenticate_user:
        user = await repo.get_by_email(db, email)
        if user is None:
            verify_password("dummy", get_timing_dummy_hash())  # burns ~250ms
            raise AuthError("INVALID_CREDENTIALS")
        if not verify_password(plain_password, user.password_hash):
            raise AuthError("INVALID_CREDENTIALS")
    """
    return _DUMMY_TIMING_GUARD_HASH


def hash_password(plain: str) -> str:
    """Hash plaintext password with bcrypt cost=12."""
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """
    Verify plaintext against bcrypt hash. Takes ~250ms at cost=12.
    Call even when user is not found (pass get_timing_dummy_hash()).
    """
    return _pwd_context.verify(plain, hashed)


# --- Complete example: login with timing protection ---

async def authenticate_user(email: str, password: str, db) -> "User":
    """
    Authenticate user with consistent ~250ms response time
    regardless of whether the email exists.

    Raises AuthError("INVALID_CREDENTIALS") for any failure.
    Never distinguishes "email not found" from "wrong password".
    """
    user = await UserRepository.get_by_email(db, email)

    if user is None:
        # Burn time so response takes ~250ms even for non-existent emails.
        # Without this, an attacker can enumerate valid emails in <1ms.
        verify_password("dummy", get_timing_dummy_hash())
        raise AuthError("INVALID_CREDENTIALS")

    if not verify_password(password, user.password_hash):
        raise AuthError("INVALID_CREDENTIALS")

    return user
