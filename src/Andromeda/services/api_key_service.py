import secrets
import base64
import shortuuid

from fastapi import HTTPException
from sqlmodel import select, col
from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession

from Andromeda.auth.hashing import hash_secret

from Andromeda.models.user import User, UserKey

from Andromeda.schemas.key import CreateKeyRequest, CreatedKeyResponse, DeletedKeyResponse, KeyPublic, KeyListResponse, KeySpecific
from Andromeda.schemas.jwt import JWTPayload


valid_user_types = ["user", "client"]
valid_type_prefixes = ["sk", "nk", "wk", "mk", "fk"]
valid_env_types = ["live", "test"]


# Utils
def _gen_secret() -> str:
    raw = secrets.token_bytes(32)
    return base64.urlsafe_b64encode(raw).rstrip(b'=').decode()


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
 

async def create_api_key(request: CreateKeyRequest, user: JWTPayload, session: AsyncSession) -> CreatedKeyResponse:
    sub_components = user.sub.split(":")

    if len(sub_components) != 2 or sub_components[0] not in valid_user_types:
        raise HTTPException(status_code=403, detail="Invalid user type")
    
    if sub_components[0] == "client":

        if not all(scope in (user.scopes or []) for scope in request.scopes):
            raise HTTPException(status_code=403, detail="Missing scopes")

        result = await session.exec(select(User).join(UserKey).where(UserKey.kid == sub_components[1]))
            
        client_user = result.one_or_none()

        if client_user is None:
            raise HTTPException(status_code=401, detail="Invalid user")

        key_id = _gen_kid()
        key_secret = _gen_secret()
        full_key = _format_key(prefix=request.type, env=request.env, kid=key_id, secret=key_secret)

        key = UserKey(user_id=client_user.id, name=request.name, kid=key_id, secret_hash=hash_secret(key_secret), scopes=request.scopes)
        session.add(key)

        try:
            await session.commit()
            await session.refresh(key)
            return CreatedKeyResponse(name=request.name, type=request.type, env=request.env, scopes=request.scopes, key=full_key)
        except IntegrityError:
            raise HTTPException(status_code=409, detail="An API key with this name already exists")
        
    elif sub_components[0] == "user":
        result = await session.exec(select(User).where(User.id == sub_components[1]))
            
        selected_user = result.one_or_none()

        if selected_user is None:
            raise HTTPException(status_code=401, detail="Invalid user")

        key_id = _gen_kid()
        key_secret = _gen_secret()
        full_key = _format_key(prefix=request.type, env=request.env, kid=key_id, secret=key_secret)

        key = UserKey(user_id=selected_user.id, name=request.name, kid=key_id, secret_hash=hash_secret(key_secret), scopes=request.scopes)
        session.add(key)

        try:
            await session.commit()
            await session.refresh(key)
            return CreatedKeyResponse(name=request.name, type=request.type, env=request.env, scopes=request.scopes, key=full_key)
        except IntegrityError:
            raise HTTPException(status_code=409, detail="An API key with this name already exists")
        
    else:
        raise HTTPException(status_code=403, detail="Invalid user type")
    

async def delete_api_key(kid: str, user: JWTPayload, session: AsyncSession) -> DeletedKeyResponse:
    sub_components = user.sub.split(":")

    if len(sub_components) != 2 or sub_components[0] != "user":
        raise HTTPException(status_code=403, detail="Invalid user type")
    
    result = await session.exec(select(UserKey).where(UserKey.user_id == sub_components[1], UserKey.kid == kid))

    selected_key = result.one_or_none()

    if selected_key is None:
        raise HTTPException(status_code=404, detail="API key not found")

    await session.delete(selected_key)
    await session.commit()

    return DeletedKeyResponse(message="API key successfully deleted")


async def list_api_keys(user: JWTPayload, session: AsyncSession) -> KeyListResponse:
    sub_components = user.sub.split(":")

    if len(sub_components) != 2 or sub_components[0] != "user":
        raise HTTPException(status_code=403, detail="Invalid user type")
    
    results = await session.exec(
        select(UserKey)
        .where(UserKey.user_id == sub_components[1])
        .order_by(col(UserKey.created_at).asc())
    )

    keys = [KeyPublic.model_validate(k) for k in results]

    return KeyListResponse(keys=keys)


async def get_api_key_info(kid: str, user: JWTPayload, session: AsyncSession) -> KeySpecific:
    sub_components = user.sub.split(":")

    if len(sub_components) != 2 or sub_components[0] != "user":
        raise HTTPException(status_code=403, detail="Invalid user type")
    
    result = await session.exec(select(UserKey).where(UserKey.user_id == sub_components[1], UserKey.kid == kid))

    selected_key = result.one_or_none()

    return KeySpecific.model_validate(selected_key)
