from datetime import datetime, timezone

from fastapi import HTTPException
from sqlmodel import select
from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession

# Security
from Andromeda.auth.hashing import hash_password

# Models
from Andromeda.models.user import User

# Schemas 
from Andromeda.schemas.user import UserCreate, UserPublic
from Andromeda.schemas.jwt import JWTPayload


async def create_user(request: UserCreate, session: AsyncSession) -> UserPublic:
    user = User(
        name = request.name,
        email = request.email,
        password_hash = hash_password(request.password),
        last_login = datetime.now(timezone.utc)
    )

    session.add(user)

    try:
        await session.commit()
        await session.refresh(user)
        return UserPublic(
            id=user.id,
            name=user.name,
            email=user.email,
            avatar=user.avatar,
            last_login=user.last_login,
            created_at=user.created_at
        )
    except IntegrityError:
        raise HTTPException(status_code=409, detail="A user with this username or email already exists")
    

async def delete_user(user: UserPublic, session: AsyncSession) -> None:
    result = await session.exec(select(User).where(User.id == user.id))
    selected_user = result.one_or_none()

    await session.delete(selected_user)


async def get_user_data(user: UserPublic, session: AsyncSession) -> UserPublic:
    result = await session.exec(select(User).where(User.id == user.id))
    user_data = result.one_or_none()

    return UserPublic.model_validate(user_data)
