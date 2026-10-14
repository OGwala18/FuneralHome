"""Staff authentication for the admin portal.

Supabase Auth issues the tokens; this module only verifies them. We never see
or store a password, and there is no shared secret to leak: Supabase signs with
ES256 and we check the signature against its PUBLIC key, fetched from the
project's JWKS endpoint.

Two gates, deliberately. A valid Supabase token proves someone signed up; it
does not prove they work here. So a verified token must ALSO carry an email on
the STAFF_EMAILS allowlist. Public sign-up should additionally be disabled in
the Supabase dashboard — the allowlist is the belt to that braces.
"""

from __future__ import annotations

import logging
import threading
import time

import jwt
from fastapi import Depends, HTTPException, Request, status
from jwt import PyJWKClient

from .config import get_settings
from .db import connection
from .services.staff import Role, resolve_or_bootstrap, role_at_least

logger = logging.getLogger(__name__)

# Tolerance for clock skew when verifying Supabase tokens. Sixty seconds is
# the usual allowance; see the note at the jwt.decode call below.
CLOCK_SKEW_LEEWAY_SECONDS = 60

# PyJWKClient caches keys internally, but the client itself is built once so a
# key rotation does not cost a fetch on every request.
_jwk_client: PyJWKClient | None = None
_jwk_lock = threading.Lock()
_jwk_created_at = 0.0
_JWK_MAX_AGE_SECONDS = 3600


def _client() -> PyJWKClient:
    global _jwk_client, _jwk_created_at
    settings = get_settings()
    if not settings.supabase_jwks_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Staff sign-in is not configured on this server.",
        )
    with _jwk_lock:
        expired = time.monotonic() - _jwk_created_at > _JWK_MAX_AGE_SECONDS
        if _jwk_client is None or expired:
            _jwk_client = PyJWKClient(settings.supabase_jwks_url, cache_keys=True)
            _jwk_created_at = time.monotonic()
        return _jwk_client


class StaffUser:
    """A verified identity plus what it is allowed to do.

    `id` is the Supabase account; `staff_id` is our own row, which is the one
    that carries the role.
    """

    __slots__ = ("id", "email", "role", "staff_id")

    def __init__(self, user_id: str, email: str, role: str, staff_id: str) -> None:
        self.id = user_id
        self.email = email
        self.role = role
        self.staff_id = staff_id

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "StaffUser(%s, %s)" % (self.email, self.role)


def _unauthorised(detail: str) -> HTTPException:
    # Always the same wording regardless of which check failed, so a probe
    # cannot learn whether an email exists or only the signature was wrong.
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_staff(request: Request) -> StaffUser:
    """FastAPI dependency. Rejects anything that is not a signed-in staff member."""
    settings = get_settings()

    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise _unauthorised("Sign in to continue.")
    token = header[7:].strip()
    if not token:
        raise _unauthorised("Sign in to continue.")

    try:
        signing_key = _client().get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256", "RS256"],
            audience="authenticated",
            issuer=settings.supabase_issuer,
            options={"require": ["exp", "sub", "aud"]},
            # Supabase stamps `iat` from its own clock. With no leeway, a staff
            # machine running even a few seconds slow sees every token as
            # issued in the future and PyJWT raises ImmatureSignatureError, so
            # nobody can sign in and the reason is invisible from the browser.
            # RFC 7519 §4.1.4 allows a small leeway for exactly this. Sixty
            # seconds absorbs ordinary drift without meaningfully extending the
            # life of a token.
            leeway=CLOCK_SKEW_LEEWAY_SECONDS,
        )
    except HTTPException:
        raise
    except jwt.ExpiredSignatureError:
        raise _unauthorised("Your session has expired. Please sign in again.")
    except jwt.ImmatureSignatureError:
        # Past the leeway, this is a real clock problem rather than a bad token,
        # so say so: "sign in again" would send someone round a loop forever.
        logger.warning(
            "Staff token rejected: issued in the future beyond %ss leeway. "
            "Check this machine's clock against UTC.",
            CLOCK_SKEW_LEEWAY_SECONDS,
        )
        raise _unauthorised(
            "This computer's clock is out of step with the sign-in service. "
            "Correct the system time, then sign in again."
        )
    except Exception as exc:  # noqa: BLE001 - any verification failure is a rejection
        logger.warning("Staff token rejected: %s", type(exc).__name__)
        raise _unauthorised("Sign in to continue.")

    email = (claims.get("email") or "").strip().lower()
    if not email:
        raise _unauthorised("Sign in to continue.")

    subject = str(claims.get("sub"))

    # A valid token proves identity, not employment. The staff table decides.
    with connection() as conn:
        record = resolve_or_bootstrap(conn, email, subject)

    if record is None:
        logger.warning("Portal access denied: account is not staff")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account is not authorised for the staff portal.",
        )

    if not record["is_active"]:
        logger.warning("Portal access denied: account is deactivated")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been deactivated. Speak to a manager.",
        )

    return StaffUser(
        user_id=subject,
        email=email,
        role=record["role"],
        staff_id=str(record["id"]),
    )


def require_role(minimum: Role):
    """Dependency factory: require at least `minimum` privilege.

    Used as `Depends(require_role("owner"))`. Kept separate from require_staff so
    the privilege needed by a route is visible in its signature.
    """

    def _check(staff: StaffUser = Depends(require_staff)) -> StaffUser:
        if not role_at_least(staff.role, minimum):
            logger.warning(
                "Denied %s action to a %s account", minimum, staff.role
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to do that.",
            )
        return staff

    return _check


StaffDep = Depends(require_staff)
