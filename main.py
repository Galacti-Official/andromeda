from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select
from uuid import UUID

# Database
from Andromeda.api.database.init_db import init_db
from Andromeda.api.database.database import engine, get_session

# Routes
from Andromeda.api.routes import auth, api_keys


# Models
from Andromeda.models.user import User, UserKey

# Schemas
from Andromeda.schemas.user import UserCreate, UserPublic
from Andromeda.schemas.jwt import JWTPayload
from Andromeda.schemas.key import CreatedKeyResponse

# Auth
from Andromeda.auth.dependancies import get_current_user, require_scope

from Andromeda.auth.hashing import hash_secret
from Andromeda.services.api_key_service import gen_kid, gen_secret, format_key
from Andromeda.api.middleware import RateLimiterMiddleware
from Andromeda.config import settings


def parse_trusted_proxies(raw: str) -> set[str]:
    return {proxy.strip() for proxy in raw.split(",") if proxy.strip()}


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    RateLimiterMiddleware,
    requests_limit=settings.rate_limit_requests,
    window_seconds=settings.rate_limit_window_seconds,
    trusted_proxy_ips=parse_trusted_proxies(settings.rate_limit_trusted_proxy_ips),
)


app.include_router(auth.router)
app.include_router(api_keys.router)



# --------------- Internal ---------------
# This section contains internal, Galacti specific functions.
# They are not publicly accessible under normal operating conditions.

@app.post("/users", response_model=UserPublic)
async def create_user(payload: UserCreate):
    async with AsyncSession(engine) as session:
        user = User.model_validate(payload)
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


@app.get("/users", response_model=list[UserPublic])
async def read_users(user: JWTPayload = Depends(require_scope("user:view"))):
    if not user:
        raise HTTPException(status_code=403, detail="Access denied, you do not have the right permissions to use this path")

    async with AsyncSession(engine) as session:
        result = await session.exec(select(User))
        users = result.all()
        return users
    
    
@app.post("/genkey", response_model=CreatedKeyResponse)
async def genkey(key_user_id: UUID, key_name: str):
    key_id = gen_kid()
    secret = gen_secret()
    key_secret_hash = hash_secret(secret)
    key_scopes = ["user:view"]
    

    key_type_prefix = "sk"
    key_env_type = "live"

    full_key = format_key(key_type_prefix, key_env_type, key_id, secret)

    async with AsyncSession(engine) as session:
        key = UserKey(user_id=key_user_id, name = key_name, kid=key_id, secret_hash=key_secret_hash, scopes=key_scopes)
        session.add(key)
        await session.commit()
        await session.refresh(key)

    return CreatedKeyResponse(name=key_name, type=key_type_prefix, env=key_env_type, scopes=key_scopes, key=full_key)



# --------------- External ---------------
# This section contains external and public functions.
# They are intended to be publicly accessible at all times.

@app.get("/")
async def root_get():
    return {"info":"Andromeda API is online.", "version":"v0.0.1"}
