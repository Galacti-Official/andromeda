from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

# Database
from Andromeda.api.database.database import get_session

# Security
from Andromeda.auth.hashing import hash_password

# Models
from Andromeda.models.user import User

# Schemas 
from Andromeda.schemas.user import UserCreate, UserPublic


async def create_user(request: UserCreate) -> UserPublic:
    async with get_session() as session:
        user = User(
            name = request.name,
            email = request.email,
            password_hash = hash_password(request.password),
            last_login = None
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


async def reset_password():
    pass
