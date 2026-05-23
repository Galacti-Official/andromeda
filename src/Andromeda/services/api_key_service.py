import secrets
import base64
import shortuuid

from datetime import datetime, timezone
from uuid import UUID

from sqlmodel import select, col
from sqlmodel.ext.asyncio.session import AsyncSession

from Andromeda.auth.hashing import hash_secret

from Andromeda.api.database.redis import redis_client
from Andromeda.api.errors import AndromedaError

from Andromeda.models.user import User, UserKey, UserKeyUsage

from Andromeda.schemas.user import UserPublic

from Andromeda.schemas.key import (
    CreateKeyRequest, CreatedKeyResponse, DeletedKeyResponse, ActivatedKeyResponse, DeactivatedKeyResponse,
    KeyPublic, KeyListResponse, KeySpecific, EditKeyRequest
)
from Andromeda.schemas.jwt import JWTPayload


valid_user_types = ["user", "client"]
valid_type_prefixes = ["sk", "nk", "wk", "mk", "fk"]
valid_env_types = ["live", "test"]


# Utils
def _gen_secret() -> str:
    raw = secrets.token_bytes(32)
    return base64.urlsafe_b64encode(raw).rstrip(b'=').decode().replace('_', '-')


def _gen_kid() -> str:
    return shortuuid.uuid()


def _format_key(prefix: str, env: str, kid: str, secret: str) -> str:
    if prefix not in valid_type_prefixes:
        raise ValueError(f"{prefix} is not a valid type prefix, use one of {valid_type_prefixes}")
    
    if env not in valid_env_types:
        raise ValueError(f"{env} is not a valid environment type, use one of {valid_env_types}")
    
    if len(kid) != 22:
        raise ValueError(f"kid must be 22 characters, got {len(kid)}")
    
    if len(secret) != 43:
        raise ValueError(f"secret must be 43 characters, got {len(secret)}")
    
    return f"{prefix}_{env}_{kid}_{secret}"


def get_user_id(user: JWTPayload | UserPublic) -> UUID | str:
    if isinstance(user, UserPublic):
        return user.id
    
    sub_components = user.sub.split(":")
    if len(sub_components) != 2:
        raise AndromedaError(400, "bad_request", "Invalid request")
    return str(sub_components[1])


async def increment_usage(kid: str):
    try:
        now = datetime.now(timezone.utc)
        hour_key = now.strftime("%Y%m%d%H")
        await redis_client.incr(f"usage:{kid}:calls:today")
        await redis_client.incr(f"usage:{kid}:calls:{hour_key}")
        await redis_client.set(f"usage:{kid}:last_used", now.isoformat())
    except Exception:
        pass


async def flush_daily_usage(session: AsyncSession):
    today = datetime.now(timezone.utc)
    
    keys = await redis_client.keys("usage:*:calls:today")
    
    for key in keys:
        kid = key.split(":")[1]
        calls = int(await redis_client.get(key) or 0)
        
        if calls == 0:
            continue
        
        usage = UserKeyUsage(kid=kid, calls=calls, date=today)
        session.add(usage)
    
    await session.commit()
    
    for key in keys:
        await redis_client.delete(key)
 

async def create_api_key(request: CreateKeyRequest, user: UserPublic, session: AsyncSession) -> CreatedKeyResponse:
    result = await session.exec(select(User).where(User.id == user.id))
            
    selected_user = result.one_or_none()

    if selected_user is None:
        raise AndromedaError(404, "not_found", "User not found")

    key_id = _gen_kid()
    key_secret = _gen_secret()
    full_key = _format_key(prefix=request.type, env=request.env, kid=key_id, secret=key_secret)

    key = UserKey(user_id=selected_user.id, name=request.name, kid=key_id, secret_hash=hash_secret(key_secret), scopes=request.scopes)

    session.add(key)
    await session.commit()
    await session.refresh(key)

    return CreatedKeyResponse(name=request.name, type=request.type, env=request.env, scopes=request.scopes, key=full_key)    
    

async def regenerate_api_key(kid: str, user: UserPublic, session: AsyncSession) -> CreatedKeyResponse:
    result = await session.exec(select(UserKey).where(UserKey.user_id == user.id, UserKey.kid == kid))

    selected_key = result.one_or_none()

    if selected_key is None:
        raise AndromedaError(404, "not_found", "API key not found")
    
    key_secret = _gen_secret()
    full_key = _format_key(prefix="sk", env="live", kid=selected_key.kid, secret=key_secret)

    selected_key.secret_hash = hash_secret(key_secret)

    session.add(selected_key)
    await session.commit()
    await session.refresh(selected_key)

    return CreatedKeyResponse(name=selected_key.name, type="sk", env="live", scopes=selected_key.scopes, key=full_key)
    
    
async def delete_api_key(kid: str, user: UserPublic, session: AsyncSession) -> DeletedKeyResponse:
    result = await session.exec(select(UserKey).where(UserKey.user_id == user.id, UserKey.kid == kid))

    selected_key = result.one_or_none()

    if selected_key is None:
        raise AndromedaError(404, "not_found", "API key not found")

    await session.delete(selected_key)
    await session.commit()

    return DeletedKeyResponse(message="API key successfully deleted")


async def list_api_keys(user: UserPublic, session: AsyncSession) -> KeyListResponse:
    results = await session.exec(
        select(UserKey)
        .where(UserKey.user_id == user.id)
        .order_by(col(UserKey.created_at).asc())
    )

    keys = [KeyPublic.model_validate(k) for k in results]

    return KeyListResponse(keys=keys)


async def get_api_key_info(kid: str, user: UserPublic, session: AsyncSession) -> KeySpecific:
    key_result = await session.exec(select(UserKey).where(UserKey.user_id == user.id, UserKey.kid == kid))

    selected_key = key_result.one_or_none()

    if selected_key is None:
        raise AndromedaError(404, "not_found", "API key not found")
    
    now = datetime.now(timezone.utc)
    hour_key = now.strftime("%Y%m%d%H")
    
    calls_today = await redis_client.get(f"usage:{kid}:calls:today") or 0
    calls_this_hour = await redis_client.get(f"usage:{kid}:calls:{hour_key}") or 0
    last_used = await redis_client.get(f"usage:{kid}:last_used")

    return KeySpecific(
        name=selected_key.name, kid=selected_key.kid, scopes=selected_key.scopes,
        created_at=selected_key.created_at, is_active=selected_key.is_active, last_used=last_used,
        calls_today=calls_today, calls_this_hour=calls_this_hour
    )


async def activate_api_key(kid: str, user: UserPublic, session: AsyncSession) -> ActivatedKeyResponse:
    result = await session.exec(select(UserKey).where(UserKey.user_id == user.id, UserKey.kid == kid))

    selected_key = result.one_or_none()

    if selected_key is None:
        raise AndromedaError(404, "not_found", "API key not found")
    
    if selected_key.is_active:
        raise AndromedaError(409, "conflict", "API key already deactivated")
    
    selected_key.is_active = True

    session.add(selected_key)
    await session.commit()

    return ActivatedKeyResponse(message="API key successfully activated")


async def deactivate_api_key(kid: str, user: UserPublic, session: AsyncSession) -> DeactivatedKeyResponse:
    result = await session.exec(select(UserKey).where(UserKey.user_id == user.id, UserKey.kid == kid))

    selected_key = result.one_or_none()

    if selected_key is None:
        raise AndromedaError(404, "not_found", "API key not found")
    
    if not selected_key.is_active:
        raise AndromedaError(409, "conflict", "API key already deactivated")
        
    selected_key.is_active = False

    session.add(selected_key)
    await session.commit()

    return DeactivatedKeyResponse(message="API key successfully deactivated")


async def edit_api_key(kid: str, user: UserPublic, request: EditKeyRequest, session: AsyncSession) -> KeySpecific:
    result = await session.exec(select(UserKey).where(UserKey.user_id == user.id, UserKey.kid == kid))

    selected_key = result.one_or_none()

    if selected_key is None:
        raise AndromedaError(404, "not_found", "API key not found")

    if request.scopes:
        selected_key.scopes = request.scopes

    if request.name:
        selected_key.name = request.name

    session.add(selected_key)
    await session.commit()

    return await get_api_key_info(kid, user, session)
