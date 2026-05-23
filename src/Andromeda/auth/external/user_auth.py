import json, jwt, secrets
from datetime import datetime, timedelta, timezone

from fastapi import Request, Response
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession as AsyncSession

from Andromeda.api.errors import AndromedaError
from Andromeda.auth.hashing import verify_secret, verify_password
from Andromeda.models.user import User, UserKey
from Andromeda.schemas.jwt import JWTPayload
from Andromeda.schemas.user import UserPublic, UserLoginRequest
from Andromeda.config import settings


COOKIE_NAME = "session"


async def set_session_cookie(request: Request, response: Response, user: UserPublic, redis_client):
    session_id = secrets.token_urlsafe(64)
    
    session_data = json.dumps({
        "user_id": str(user.id),
        "user_agent": request.headers.get("user-agent"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "last_used_at": datetime.now(timezone.utc).isoformat()
    })

    await redis_client.setex(
        f"session:{session_id}",
        86400,
        session_data
    )

    await redis_client.sadd(f"user_sessions:{user.id}", session_id)
    await redis_client.expire(f"user_sessions:{user.id}", 86400)

    response.set_cookie(
        key=COOKIE_NAME,
        value=session_id,
        httponly=True,
        secure=not settings.debug,
        samesite="strict",
        max_age=86400,
    )


async def revoke_session(request: Request, response: Response, redis_client):
    session_id = request.cookies.get(COOKIE_NAME)
    if session_id:
        raw = await redis_client.get(f"session:{session_id}")
        if raw:
            data = json.loads(raw)
            await redis_client.srem(f"user_sessions:{data['user_id']}", session_id)
        await redis_client.delete(f"session:{session_id}")
    response.delete_cookie(COOKIE_NAME)


async def revoke_specific_session(session_id: str, user: UserPublic, redis_client):
    await redis_client.srem(f"user_sessions:{user.id}", session_id)
    await redis_client.delete(f"session:{session_id}")


async def revoke_all_sessions(user: UserPublic, redis_client):
    session_ids = await redis_client.smembers(f"user_sessions:{user.id}")
    for session_id in session_ids:
        await redis_client.delete(f"session:{session_id}")
    await redis_client.delete(f"user_sessions:{user.id}")


async def auth_user_login(request: UserLoginRequest, session: AsyncSession) -> UserPublic:
    result = await session.exec(select(User).where(User.email == request.email))
    user = result.one_or_none()

    password_ok = verify_password(
        user.password_hash if user else settings.dummy_password_hash,
        request.password
    )

    if user is None or not user.is_active or not password_ok:
        raise AndromedaError(401, "unauthorized", "Invalid email or password")
        
    user.last_login = datetime.now(timezone.utc)
    session.add(user)
    await session.commit()

    return UserPublic.model_validate(user)


def issue_token(sub_type: str, sub: str, scopes: list[str] | None = None) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": f"{sub_type}:{sub}",
            "scopes": scopes or [],
            "iss": settings.user_jwt_iss,
            "aud": settings.user_jwt_aud,
            "iat": now,
            "nbf": now,
            "exp": now + timedelta(hours=1)             
        },
        key = settings.jwt_private_key,
        algorithm = "RS256"
    )


async def auth_user_key(key: str, session: AsyncSession) -> str:
    key_components = key.split("_")

    if len(key_components) != 4 or key_components[0] != "sk" or key_components[1] != "live":
        raise AndromedaError(401, "unauthorized", "Invalid API key")
    
    result = await session.exec(select(UserKey).where(UserKey.kid == key_components[2]))
    user_key = result.one_or_none()

    if user_key is None or not user_key.is_active:
        raise AndromedaError(401, "unauthorized", "Invalid API key")

    if not verify_secret(user_key.secret_hash, key_components[3]):
        raise AndromedaError(401, "unauthorized", "Invalid API key")
        
    return issue_token(sub_type="client", sub=user_key.kid, scopes=user_key.scopes)


def verify_jwt(token: str) -> JWTPayload:
    try:
        decoded = jwt.decode(
            token,
            settings.jwt_public_key,
            issuer=settings.user_jwt_iss,
            audience=settings.user_jwt_aud,
            options={
                "verify_signature": True,
                "verify_exp": True,
                "verify_iat": True,
                "verify_nbf": True,
                "require": ["sub", "exp", "iat", "nbf", "iss", "aud", "scopes"]
            },
            algorithms=["RS256"]
        )
        return JWTPayload(**decoded)
    except jwt.exceptions.PyJWTError:
        raise AndromedaError(401, "unauthorized", "Invalid token")
