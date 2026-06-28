import secrets
from datetime import datetime, timezone
from urllib.parse import urlencode

import httpx
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from Andromeda.api.errors import AndromedaError
from Andromeda.models.user import User
from Andromeda.schemas.user import UserPublic
from Andromeda.config import settings


_GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"


def build_google_authorize_url(state: str) -> str:
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "online",
    }
    return f"{_GOOGLE_AUTH_URL}?{urlencode(params)}"


async def generate_oauth_state(redis_client) -> str:
    state = secrets.token_urlsafe(32)
    await redis_client.setex(f"oauth_state:{state}", 300, "1")
    return state


async def validate_oauth_state(state: str, redis_client) -> None:
    deleted = await redis_client.delete(f"oauth_state:{state}")
    if not deleted:
        raise AndromedaError(400, "bad_request", "Invalid or expired OAuth state")


async def _exchange_code_for_token(code: str) -> str:
    async with httpx.AsyncClient() as client:
        response = await client.post(_GOOGLE_TOKEN_URL, data={
            "code": code,
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "redirect_uri": settings.google_redirect_uri,
            "grant_type": "authorization_code",
        })
    if response.status_code != 200:
        raise AndromedaError(401, "unauthorized", "Failed to exchange Google authorization code")
    return response.json()["access_token"]


async def _get_google_user_info(access_token: str) -> dict:
    async with httpx.AsyncClient() as client:
        response = await client.get(
            _GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"}
        )
    if response.status_code != 200:
        raise AndromedaError(401, "unauthorized", "Failed to retrieve Google user info")
    return response.json()


async def auth_user_google(code: str, session: AsyncSession) -> UserPublic:
    access_token = await _exchange_code_for_token(code)
    info = await _get_google_user_info(access_token)

    google_id: str = info["sub"]
    email: str = info.get("email", "")
    name: str = info.get("name", email.split("@")[0])
    avatar: str = info.get("picture", "https://cdn.galacti.org/avatars/default.png")

    result = await session.exec(select(User).where(User.google_id == google_id))
    user = result.one_or_none()

    if user is not None and not user.email_verified:
        user.email_verified = True

    if user is None:
        result = await session.exec(select(User).where(User.email == email))
        user = result.one_or_none()
        if user is not None:
            user.google_id = google_id
            user.email_verified = True

    if user is None:
        user = User(
            name=name,
            email=email,
            google_id=google_id,
            avatar=avatar,
            email_verified=True,
        )
        session.add(user)

    if not user.is_active:
        raise AndromedaError(401, "unauthorized", "Account is disabled")
    


    user.last_login = datetime.now(timezone.utc)
    session.add(user)
    await session.commit()
    await session.refresh(user)

    return UserPublic.model_validate(user)
