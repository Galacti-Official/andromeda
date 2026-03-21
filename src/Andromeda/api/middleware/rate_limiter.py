import asyncio
import math
import time
from collections import deque

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


class RateLimiterMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        requests_limit: int,
        window_seconds: int,
        trusted_proxy_ips: set[str] | None = None,
    ):
        super().__init__(app)
        self.requests_limit = requests_limit
        self.window_seconds = window_seconds
        self._buckets: dict[str, deque[float]] = {}
        self._bucket_locks: dict[str, asyncio.Lock] = {}
        self._bucket_last_seen: dict[str, float] = {}
        self._bucket_inflight: dict[str, int] = {}
        self._maps_lock = asyncio.Lock()
        self._trusted_proxy_ips = trusted_proxy_ips or set()
        self._cleanup_counter = 0

    async def dispatch(self, request: Request, call_next):
        identifier = self._get_identifier(request)
        now = time.monotonic()
        wall_now = time.time()

        async with self._maps_lock:
            lock = self._bucket_locks.setdefault(identifier, asyncio.Lock())
            bucket = self._buckets.setdefault(identifier, deque())
            self._bucket_last_seen[identifier] = now
            self._bucket_inflight[identifier] = (
                self._bucket_inflight.get(identifier, 0) + 1
            )
            self._maybe_cleanup(now)

        try:
            async with lock:
                self._prune(bucket, now)

                if len(bucket) >= self.requests_limit:
                    retry_after = max(
                        1, math.ceil(self.window_seconds - (now - bucket[0]))
                    )
                    # Buckets use monotonic time for correctness; header is wall-clock epoch
                    # for client interoperability, so this is a best-effort conversion.
                    reset_epoch = math.ceil(wall_now + retry_after)
                    headers = self._build_headers(remaining=0, reset_epoch=reset_epoch)
                    headers["Retry-After"] = str(retry_after)
                    return JSONResponse(
                        status_code=429,
                        content={"detail": "Rate limit exceeded. Please retry later."},
                        headers=headers,
                    )

                bucket.append(now)
                remaining = max(0, self.requests_limit - len(bucket))
                reset_seconds = max(
                    1, math.ceil(self.window_seconds - (now - bucket[0]))
                )
                # With a fresh bucket this will be near full window length by design.
                reset_epoch = math.ceil(wall_now + reset_seconds)
                headers = self._build_headers(
                    remaining=remaining, reset_epoch=reset_epoch
                )
        finally:
            async with self._maps_lock:
                inflight = self._bucket_inflight.get(identifier, 0)
                if inflight <= 1:
                    self._bucket_inflight.pop(identifier, None)
                else:
                    self._bucket_inflight[identifier] = inflight - 1

        response = await call_next(request)
        response.headers.update(headers)
        return response

    def _prune(self, bucket: deque[float], now: float) -> None:
        cutoff = now - self.window_seconds
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()

    def _cleanup(self, now: float) -> None:
        cutoff = now - self.window_seconds
        stale_keys = [
            key
            for key, last_seen in self._bucket_last_seen.items()
            if last_seen <= cutoff and self._bucket_inflight.get(key, 0) == 0
        ]
        for key in stale_keys:
            self._buckets.pop(key, None)
            self._bucket_last_seen.pop(key, None)
            self._bucket_locks.pop(key, None)

    def _maybe_cleanup(self, now: float) -> None:
        self._cleanup_counter += 1
        if self._cleanup_counter >= 250:
            self._cleanup(now)
            self._cleanup_counter = 0

    def _get_identifier(self, request: Request) -> str:
        direct_host = request.client.host if request.client else None

        if direct_host and direct_host in self._trusted_proxy_ips:
            forwarded_for = request.headers.get("x-forwarded-for")
            if forwarded_for:
                # We rely on trusted proxies to overwrite or normalize this header.
                forwarded_ip = forwarded_for.split(",")[0].strip()
                if forwarded_ip:
                    return forwarded_ip

        if direct_host:
            return direct_host

        # All unidentifiable clients share this fallback bucket.
        return "unknown"

    def _build_headers(self, remaining: int, reset_epoch: int) -> dict[str, str]:
        return {
            "X-RateLimit-Limit": str(self.requests_limit),
            "X-RateLimit-Remaining": str(remaining),
            "X-RateLimit-Reset": str(reset_epoch),
        }
