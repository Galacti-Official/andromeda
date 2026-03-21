import pytest
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI

from Andromeda.api.middleware import RateLimiterMiddleware


def build_test_app(*, requests_limit: int = 3, window_seconds: int = 60, trusted_proxy_ips: set[str] | None = None):
    """Minimal FastAPI app with the rate limiter attached."""
    app = FastAPI()

    app.add_middleware(
        RateLimiterMiddleware,
        requests_limit=requests_limit,
        window_seconds=window_seconds,
        trusted_proxy_ips=trusted_proxy_ips or set(),
    )

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    return app


@pytest.mark.asyncio
class TestRateLimiterMiddleware:

    async def test_request_within_limit_passes(self):
        app = build_test_app(requests_limit=3)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/ping")

        assert response.status_code == 200

    async def test_ratelimit_headers_present(self):
        app = build_test_app(requests_limit=3)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/ping")

        assert "x-ratelimit-limit" in response.headers
        assert "x-ratelimit-remaining" in response.headers
        assert "x-ratelimit-reset" in response.headers

    async def test_remaining_decrements(self):
        app = build_test_app(requests_limit=3)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r1 = await client.get("/ping")
            r2 = await client.get("/ping")

        assert int(r1.headers["x-ratelimit-remaining"]) > int(r2.headers["x-ratelimit-remaining"])

    async def test_request_over_limit_rejected(self):
        # Fill the bucket, then one more request should be rejected.
        app = build_test_app(requests_limit=3)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            for _ in range(3):
                await client.get("/ping")
            response = await client.get("/ping")

        assert response.status_code == 429

    async def test_429_response_has_retry_after_header(self):
        app = build_test_app(requests_limit=3)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            for _ in range(3):
                await client.get("/ping")
            response = await client.get("/ping")

        assert response.status_code == 429
        assert "retry-after" in response.headers
        assert int(response.headers["retry-after"]) > 0

    async def test_429_remaining_is_zero(self):
        app = build_test_app(requests_limit=3)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            for _ in range(3):
                await client.get("/ping")
            response = await client.get("/ping")

        assert response.headers["x-ratelimit-remaining"] == "0"

    async def test_different_ips_have_separate_buckets(self):
        app = build_test_app(requests_limit=3, trusted_proxy_ips={"127.0.0.1"})

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            for _ in range(3):
                await client.get("/ping", headers={"X-Forwarded-For": "1.2.3.4"})
            response = await client.get("/ping", headers={"X-Forwarded-For": "9.9.9.9"})

        assert response.status_code == 200

    async def test_trusted_proxy_uses_forwarded_ip(self):
        app = build_test_app(requests_limit=3, trusted_proxy_ips={"127.0.0.1"})

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            for _ in range(3):
                await client.get("/ping", headers={"X-Forwarded-For": "1.2.3.4"})
            blocked = await client.get("/ping", headers={"X-Forwarded-For": "1.2.3.4"})
            allowed = await client.get("/ping", headers={"X-Forwarded-For": "5.6.7.8"})

        assert blocked.status_code == 429
        assert allowed.status_code == 200
