from contextlib import asynccontextmanager

from fastapi import FastAPI

from Andromeda.api.database.init_db import init_db

from Andromeda.api.routes import auth, api_keys, status

from Andromeda.api.middleware import RateLimiterMiddleware
from Andromeda.config import settings


def parse_trusted_proxies(raw: str) -> set[str]:
    return {proxy.strip() for proxy in raw.split(",") if proxy.strip()}


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    lifespan=lifespan,
    openapi_url=None if settings.production else "/openapi.json",
    docs_url=None if settings.production else "/docs",
    redoc_url=None if settings.production else "/redoc",
)


app.add_middleware(
    RateLimiterMiddleware,
    requests_limit=settings.rate_limit_requests,
    window_seconds=settings.rate_limit_window_seconds,
    trusted_proxy_ips=parse_trusted_proxies(settings.rate_limit_trusted_proxy_ips),
)


app.include_router(auth.router)
app.include_router(api_keys.router)
app.include_router(status.router)


# --------------- External ---------------
# This section contains external and public functions.
# They are intended to be publicly accessible at all times.

@app.get("/")
async def root_get():
    return {"info":"Andromeda API is online.", "version": settings.version}
