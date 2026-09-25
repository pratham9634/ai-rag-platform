"""
API Rate Limiting Module.

Provides sliding-window rate limiting per tenant/client to prevent DoS attacks,
brute-force abuse, and runaway LLM token consumption.
Supports in-memory tracking with automatic window sliding and Redis integration readiness.
"""

import time
from collections import defaultdict
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from app.auth.security import AuthenticatedUser, get_current_user

# In-memory timestamp storage: { "scope:key": [timestamp1, timestamp2, ...] }
_REQUEST_HISTORY: dict[str, list[float]] = defaultdict(list)


def clean_old_requests(
    timestamps: list[float], window_seconds: float, current_time: float
) -> list[float]:
    """Prune timestamps older than the sliding window."""
    cutoff = current_time - window_seconds
    return [t for t in timestamps if t > cutoff]


def reset_rate_limits() -> None:
    """Clear in-memory rate limits (primarily used in unit test setup/teardown)."""
    _REQUEST_HISTORY.clear()


class RateLimiter:
    """
    Sliding-window rate limiter dependency.

    Enforces a maximum number of requests allowed within a specified time window.
    Limits are partitioned by scope (e.g. 'chat', 'upload', 'retrieval') and
    client identity (verified tenant_id or client IP address).
    """

    def __init__(
        self,
        requests_per_minute: int = 60,
        window_seconds: int = 60,
        scope: str = "general",
    ) -> None:
        self.requests_per_minute = requests_per_minute
        self.window_seconds = window_seconds
        self.scope = scope

    async def __call__(
        self,
        request: Request,
        user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    ) -> None:
        """Evaluate rate limit for current client request."""
        # Partition by tenant_id if authenticated; fallback to client host IP
        client_key = (
            user.tenant_id
            if user and user.tenant_id
            else (request.client.host if request.client else "unknown")
        )
        rate_key = f"{self.scope}:{client_key}"
        now = time.time()

        # Retrieve and prune existing timestamps in window
        history = clean_old_requests(_REQUEST_HISTORY[rate_key], self.window_seconds, now)

        if len(history) >= self.requests_per_minute:
            # Calculate remaining cooldown time
            oldest_timestamp = history[0]
            retry_after = int(self.window_seconds - (now - oldest_timestamp)) + 1
            detail_msg = (
                f"Rate limit exceeded for {self.scope}. "
                f"Limit: {self.requests_per_minute} req/{self.window_seconds}s. "
                f"Try again in {retry_after}s."
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=detail_msg,
                headers={"Retry-After": str(max(1, retry_after))},
            )

        # Record this request
        history.append(now)
        _REQUEST_HISTORY[rate_key] = history
