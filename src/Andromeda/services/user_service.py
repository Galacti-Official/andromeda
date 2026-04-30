from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession

# Security
from Andromeda.auth.hashing import hash_password

# Models
from Andromeda.models.user import User

# Schemas 
from Andromeda.schemas.user import UserCreate, UserPublic


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
        raise HTTPException(status_code=409, detail="User with this username or email already exists")

