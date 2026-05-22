import json
import user_agents as ua
from datetime import datetime, timezone

from fastapi import Request
from sqlmodel import select
from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession

from Andromeda.api.errors import AndromedaError

from Andromeda.auth.hashing import hash_password
from Andromeda.auth.external.user_auth import revoke_all_sessions

from Andromeda.models.user import User

from Andromeda.schemas.user import UserCreate, UserPublic, UserSession, UserSessions


COOKIE_NAME = "session"


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
        raise AndromedaError(409, "conflict", "A user with this username or email already exists")
    

async def delete_user(user: UserPublic, session: AsyncSession, redis_client) -> None:
    result = await session.exec(select(User).where(User.id == user.id))
    selected_user = result.one_or_none()

    await revoke_all_sessions(user, redis_client)

    await session.delete(selected_user)
    await session.commit()


async def get_user_sessions(user: UserPublic, request: Request, redis_client) -> UserSessions:
    session_ids = await redis_client.smembers(f"user_sessions:{user.id}")
    current_session_id = request.cookies.get(COOKIE_NAME)

    sessions = []

    for session_id in session_ids:
        raw = await redis_client.get(f"session:{session_id}")

        if raw:
            data = json.loads(raw)

            user_agent = ua.parse(data["user_agent"])

            session = UserSession(
                session_id=session_id,
                current_session_id=str(current_session_id),
                is_current_session=True if session_id == current_session_id else False,
                created_at=data["created_at"],
                last_used_at=data["last_used_at"],
                browser=user_agent.browser.family,
                os=user_agent.os.family,
                device_type=user_agent.device.family
            )

            sessions.append(session)

    return UserSessions(sessions=sessions)


async def get_user_data(user: UserPublic, session: AsyncSession) -> UserPublic:
    result = await session.exec(select(User).where(User.id == user.id))
    user_data = result.one_or_none()

    if not user_data:
        raise AndromedaError(404, "not_found", "Selected user not found")

    return UserPublic(
        id=user_data.id, name=user_data.name, email=user_data.email,
        avatar=user_data.avatar, last_login=user_data.last_login, created_at=user_data.created_at
    )
