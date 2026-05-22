import asyncio, json

from uuid import UUID
from fastapi import Request, Response, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select

from Andromeda.auth.external.user_auth import verify_jwt
from Andromeda.api.errors import AndromedaError
from Andromeda.api.database.redis import redis_client
from Andromeda.api.database.database import get_session
from Andromeda.models.user import User
from Andromeda.schemas.user import UserPublic
from Andromeda.schemas.jwt import JWTPayload
from Andromeda.services.api_key_service import increment_usage
from Andromeda.config import settings


COOKIE_NAME = "session"
security = HTTPBearer(auto_error=False)


async def get_session_user(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session)
) -> UserPublic:
    session_id = request.cookies.get(COOKIE_NAME)
    
    if not session_id:
        raise AndromedaError(401, "unauthorized", "Not authenticated")
    
    raw = await redis_client.get(f"session:{session_id}")
    
    if not raw:
        raise AndromedaError(401, "unauthorized", "Not authenticated")
    
    data = json.loads(raw)
    user_id = UUID(data["user_id"])
    
    if not user_id:
        raise AndromedaError(401, "unauthorized", "Not authenticated")
    
    result = await session.exec(select(User).where(User.id == user_id))
    user = result.one_or_none()
    
    if not user or not user.is_active:
        raise AndromedaError(401, "unauthorized", "Not authenticated")
    
    await redis_client.expire(f"session:{session_id}", 86400)

    response.set_cookie(
        key=COOKIE_NAME,
        value=session_id,
        httponly=True,
        secure=not settings.debug,
        samesite="strict",
        max_age=86400
    )

    return UserPublic.model_validate(user)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security)
) -> JWTPayload:
    if not credentials:
        raise AndromedaError(401, "unauthorized", "Not authenticated")
    
    user = verify_jwt(credentials.credentials)

    sub_components = user.sub.split(":")
    if sub_components[0] == "client":
        asyncio.create_task(increment_usage(sub_components[1]))

    return user


def require_scope(scope: str):
    def check_scope(user: JWTPayload = Depends(get_current_user)) -> JWTPayload:
        if user.scopes is None or scope not in user.scopes:
            raise AndromedaError(403, "forbidden", "Insufficient permissions")
        return user
    return check_scope
