from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlmodel.ext.asyncio.session import AsyncSession
from prometheus_fastapi_instrumentator import Instrumentator

from Andromeda.api.database.init_db import init_db
from Andromeda.api.database.database import engine

from Andromeda.api.routes import auth, api_keys, status, notifications

from Andromeda.api.middleware import RateLimiterMiddleware
from Andromeda.config import settings

from Andromeda.services.health_service import start_scheduler, stop_scheduler

from Andromeda.models.status import Service, ServiceGroup, ServiceStatus


INITIAL_GROUPS = [
    ServiceGroup(id="core", name="Core Services"),
]

INITIAL_SERVICES = [
    Service(id="website", group_id="core", name="Website", status=ServiceStatus.operational,
            check_url="https://galacti.org/", healthy_codes=[200, 301, 302]),
    Service(id="dashboard", group_id="core", name="Dashboard", status=ServiceStatus.operational,
            check_url="https://dashboard.galacti.org/", healthy_codes=[200, 301, 302, 307]),
    Service(id="api", group_id="core", name="API", status=ServiceStatus.operational,
            check_url="https://api.galacti.org/", healthy_codes=[200]),
]


async def seed_services() -> None:
    async with AsyncSession(engine) as session:
        for group in INITIAL_GROUPS:
            existing = await session.get(ServiceGroup, group.id)
            if not existing:
                session.add(group)

        for service in INITIAL_SERVICES:
            existing = await session.get(Service, service.id)
            if not existing:
                session.add(service)
            else:
                # Always sync check config so URL/code changes take effect on redeploy.
                existing.check_url = service.check_url
                existing.healthy_codes = service.healthy_codes
                session.add(existing)

        await session.commit()
        

def parse_trusted_proxies(raw: str) -> set[str]:
    return {proxy.strip() for proxy in raw.split(",") if proxy.strip()}


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await seed_services()
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(
    lifespan=lifespan,
    openapi_url=None if settings.production else "/openapi.json",
    docs_url=None if settings.production else "/docs",
    redoc_url=None if settings.production else "/redoc",
)


Instrumentator().instrument(app).expose(app, endpoint="/metrics")


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
