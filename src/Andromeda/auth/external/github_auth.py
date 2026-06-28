from datetime import datetime, timezone
from urllib.parse import urlencode

import httpx
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from Andromeda.api.errors import AndromedaError
from Andromeda.auth.external.oauth import generate_oauth_state, validate_oauth_state
from Andromeda.models.user import User
from Andromeda.schemas.user import UserPublic
from Andromeda.config import settings

__all__ = ["auth_user_github", "build_github_authorize_url", "generate_oauth_state", "validate_oauth_state"]

_GITHUB_AUTH_URL = "https://github.com/login/oauth/authorize"
_GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
_GITHUB_USER_URL = "https://api.github.com/user"
_GITHUB_EMAILS_URL = "https://api.github.com/user/emails"


def build_github_authorize_url(state: str) -> str:
    params = {
        "client_id": settings.github_client_id,
        "redirect_uri": settings.github_redirect_uri,
        "scope": "read:user user:email",
        "state": state,
    }
    return f"{_GITHUB_AUTH_URL}?{urlencode(params)}"


async def _exchange_code_for_token(code: str) -> str:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            _GITHUB_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.github_client_id,
                "client_secret": settings.github_client_secret,
                "redirect_uri": settings.github_redirect_uri,
            },
            headers={"Accept": "application/json"},
        )
    if response.status_code != 200 or "access_token" not in response.json():
        raise AndromedaError(401, "unauthorized", "Failed to exchange GitHub authorization code")
    return response.json()["access_token"]


async def _get_github_user_info(access_token: str) -> dict:
    headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}
    async with httpx.AsyncClient() as client:
        user_resp = await client.get(_GITHUB_USER_URL, headers=headers)
        if user_resp.status_code != 200:
            raise AndromedaError(401, "unauthorized", "Failed to retrieve GitHub user info")
        info = user_resp.json()

        # GitHub may not expose email on /user if the user set it to private
        if not info.get("email"):
            emails_resp = await client.get(_GITHUB_EMAILS_URL, headers=headers)
            if emails_resp.status_code == 200:
                primary = next(
                    (e["email"] for e in emails_resp.json() if e.get("primary") and e.get("verified")),
                    None,
                )
                info["email"] = primary

    return info


async def auth_user_github(code: str, session: AsyncSession) -> UserPublic:
    access_token = await _exchange_code_for_token(code)
    info = await _get_github_user_info(access_token)

    github_id: str = str(info["id"])
    email: str = info.get("email") or ""
    name: str = info.get("name") or info.get("login", "")
    avatar: str = info.get("avatar_url", "https://cdn.galacti.org/avatars/default.png")

    if not email:
        raise AndromedaError(400, "bad_request", "A verified email address is required to sign in with GitHub")

    result = await session.exec(select(User).where(User.github_id == github_id))
    user = result.one_or_none()

    if user is not None and not user.email_verified:
        user.email_verified = True

    if user is None:
        result = await session.exec(select(User).where(User.email == email))
        user = result.one_or_none()
        if user is not None:
            user.github_id = github_id
            user.email_verified = True

    if user is None:
        user = User(
            name=name,
            email=email,
            github_id=github_id,
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
