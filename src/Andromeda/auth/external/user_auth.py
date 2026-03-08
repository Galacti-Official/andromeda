from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlmodel import select
import jwt

from Andromeda.auth.hashing import verify_secret, verify_password
from Andromeda.api.database.database import engine, get_session
from Andromeda.models.user import User, UserKey
from Andromeda.schemas.jwt import JWTPayload
from Andromeda.schemas.user import UserPublic, UserLoginRequest, UserLoginResponse
from Andromeda.config import settings


COOKIE_NAME = "session"


async def issue_token(sub_type: str, sub: str, scopes: list[str] | None) -> str:
    encoded_jwt = jwt.encode(
            {
                "sub": f"{sub_type}:{sub}",
                "scopes": scopes,
                "iss": settings.user_jwt_iss,
                "aud": settings.user_jwt_aud,
                "iat": datetime.now(timezone.utc),
                "nbf": datetime.now(timezone.utc),
                "exp": datetime.now(timezone.utc) + timedelta(hours=1)             
            },
            key = settings.jwt_private_key,
            algorithm = "RS256"
        )
    
    return encoded_jwt


async def set_session_cookie(response, sub: str, scopes: list[str]):
    token = await issue_token(sub_type="user", sub=sub, scopes=scopes)

    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        secure=False,
        samesite="strict",
        max_age=3600,
    )


async def auth_user_key(key: str):
    key_components = key.split("_")

    if len(key_components) != 4:
        raise HTTPException(status_code=401, detail="Invalid API key")

    if key_components[0] != "sk":
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    if key_components[1] != "live":
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    async with get_session() as session:
        result = await session.exec(select(UserKey).where(UserKey.kid == key_components[2]))
        user_key = result.one_or_none()

        if user_key is None:
            raise HTTPException(status_code=401, detail="Invalid API key")

        if not user_key.is_active:
            raise HTTPException(status_code=401, detail="Invalid API key")

        if not verify_secret(user_key.secret_hash, key_components[3]):
            raise HTTPException(status_code=401, detail="Invalid API key")

    return await issue_token(sub_type="client", sub=user_key.kid, scopes=user_key.scopes)


async def auth_user_login(request: UserLoginRequest) -> UserPublic:
    async with get_session() as session:
        result = await session.exec(select(User).where(User.email == request.email))
        user = result.one_or_none()

        if user is None:
            raise HTTPException(status_code=401, detail="User with this email does not exist")
        
        if not user.is_active:
            raise HTTPException(status_code=401, detail="This user has been deactivated")

        if not verify_password(user.password_hash, request.password):
            raise HTTPException(status_code=403, detail="Password incorrect")

        return UserPublic(
                id=user.id,
                name=user.name,
                email=user.email,
                avatar=user.avatar,
                last_login=user.last_login,
                created_at=user.created_at
            )
        

async def verify_jwt(token: str) -> JWTPayload:
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
            algorithm="RS256"
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