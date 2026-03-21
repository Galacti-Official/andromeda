from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession as AsyncSession
import jwt

from Andromeda.auth.hashing import verify_secret, verify_password
from Andromeda.models.user import User, UserKey
from Andromeda.schemas.jwt import JWTPayload
from Andromeda.schemas.user import UserPublic, UserLoginRequest
from Andromeda.config import settings


COOKIE_NAME = "session"


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


def set_session_cookie(response, sub: str, scopes: list[str]):
    token = issue_token(sub_type="user", sub=sub, scopes=scopes)

    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        secure=not settings.debug,
        samesite="strict",
        max_age=3600,
    )


async def auth_user_key(key: str, session: AsyncSession) -> str:
    key_components = key.split(".")

    if len(key_components) != 4 or key_components[0] != "sk" or key_components[1] != "live":
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    result = await session.exec(select(UserKey).where(UserKey.kid == key_components[2]))
    user_key = result.one_or_none()

    if user_key is None or not user_key.is_active:
        raise HTTPException(status_code=401, detail="Invalid API key")

    if not verify_secret(user_key.secret_hash, key_components[3]):
        raise HTTPException(status_code=401, detail="Invalid API key")
        
    return issue_token(sub_type="client", sub=user_key.kid, scopes=user_key.scopes)


async def auth_user_login(request: UserLoginRequest, session: AsyncSession) -> UserPublic:
    result = await session.exec(select(User).where(User.email == request.email))
    user = result.one_or_none()

    password_ok = verify_password(
        user.password_hash if user else settings.dummy_password_hash,
        request.password
    )

    if user is None or not user.is_active or not password_ok:
        raise HTTPException(status_code=401, detail="Invalid email or password")
        
    user.last_login = datetime.now(timezone.utc)
    session.add(user)
    await session.commit()

    return UserPublic.model_validate(user)
        

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
    except jwt.exceptions.ExpiredSignatureError:
        raise HTTPException(401, "Token expired")
    except jwt.exceptions.InvalidAudienceError:
        raise HTTPException(401, "Invalid audience")
    except jwt.exceptions.InvalidIssuerError:
        raise HTTPException(401, "Invalid issuer")
    except jwt.exceptions.PyJWTError:
        raise HTTPException(401, "Invalid token")
