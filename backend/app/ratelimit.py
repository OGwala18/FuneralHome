"""Rate limiting for the public enquiry endpoints.

The registration form is unauthenticated by necessity — a grieving family
should not have to make an account to ask about cover. That makes it the one
place a stranger can write to the database and to the office inbox, so it needs
a ceiling.

Implementation is a deliberately small in-process sliding window. It is enough
for a single API instance, which is what this system runs today.

LIMITATION worth knowing before scaling: the counters live in this process's
memory. Run two API instances and each gets its own allowance; restart the
process and the window resets. When a second instance is added, move this to
Redis rather than raising the limits.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status


class SlidingWindowLimiter:
    """Allow at most `limit` requests per `window_seconds` per key."""

    def __init__(self, limit: int, window_seconds: int) -> None:
        self._limit = limit
        self._window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> tuple[bool, int]:
        """Return (allowed, seconds_until_retry)."""
        now = time.monotonic()
        cutoff = now - self._window

        with self._lock:
            hits = self._hits[key]
            while hits and hits[0] < cutoff:
                hits.popleft()

            if len(hits) >= self._limit:
                retry_after = int(hits[0] + self._window - now) + 1
                return False, max(retry_after, 1)

            hits.append(now)

            # Opportunistic cleanup so an attacker cycling IPs cannot grow this
            # dict without bound.
            if len(self._hits) > 10_000:
                for stale_key in [k for k, v in self._hits.items() if not v or v[-1] < cutoff]:
                    del self._hits[stale_key]

            return True, 0


def client_key(request: Request) -> str:
    """Identify the caller.

    Behind a reverse proxy the socket address is the proxy, so the first hop in
    X-Forwarded-For is used when present. That header is caller-controlled and
    trivially spoofed, so this is a courtesy for honest clients and a speed bump
    for others — it is NOT an identity control. Only trust it because the only
    thing gated by it is a request count.
    """
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# Six enquiries an hour from one address is far above real human use — a family
# submits once — while still leaving room for a shared office or school network.
lead_limiter = SlidingWindowLimiter(limit=6, window_seconds=3600)

# Stage 2 is more forgiving: the same person may legitimately correct and
# resubmit their application a few times.
application_limiter = SlidingWindowLimiter(limit=20, window_seconds=3600)


def enforce(limiter: SlidingWindowLimiter, request: Request) -> None:
    allowed, retry_after = limiter.check(client_key(request))
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                "We have received several enquiries from this connection. "
                "Please phone or WhatsApp us and we will capture your details for you."
            ),
            headers={"Retry-After": str(retry_after)},
        )
