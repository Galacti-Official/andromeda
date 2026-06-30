import json
import user_agents as ua
from datetime import datetime, timezone

from fastapi import Request
from sqlmodel import select
from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession

from Andromeda.api.errors import AndromedaError

from Andromeda.auth.hashing import hash_password, verify_password
from Andromeda.auth.external.user_auth import revoke_all_sessions

from Andromeda.models.user import User

from Andromeda.schemas.user import UserCreate, UserPublic, UserEditRequest, UserChangePasswordRequest,  UserChangePasswordResponse, UserSession, UserSessions
from Andromeda.services.email_service import send_verification_email, consume_verification_token


COOKIE_NAME = "session"


async def create_user(request: UserCreate, session: AsyncSession, redis_client) -> UserPublic:
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
    except IntegrityError:
        raise AndromedaError(409, "conflict", "A user with this username or email already exists")

    await send_verification_email(str(user.id), user.email, redis_client)

    return UserPublic.model_validate(user)


async def verify_user_email(token: str, session: AsyncSession, redis_client) -> None:
    user_id = await consume_verification_token(token, redis_client)
    if not user_id:
        raise AndromedaError(400, "bad_request", "Invalid or expired verification token")

    result = await session.exec(select(User).where(User.id == user_id))
    user = result.one_or_none()

    if not user:
        raise AndromedaError(404, "not_found", "User not found")

    if user.email_verified:
        return

    user.email_verified = True
    session.add(user)
    await session.commit()


async def request_verification_email(user: UserPublic, redis_client) -> None:
    await send_verification_email(str(user.id), user.email, redis_client)
    

async def delete_user(user: UserPublic, session: AsyncSession, redis_client) -> None:
    result = await session.exec(select(User).where(User.id == user.id))
    selected_user = result.one_or_none()

    await revoke_all_sessions(user, redis_client)

    await session.delete(selected_user)
    await session.commit()


async def edit_user(request: UserEditRequest, user: UserPublic, session: AsyncSession) -> UserPublic:
    result = await session.exec(select(User).where(User.id == user.id))
    selected_user = result.one_or_none()

    if selected_user is None:
        raise AndromedaError(404, "not_found", "Selected user not found")

    if request.name:
        selected_user.name = request.name

    session.add(selected_user)
    await session.commit()
    await session.refresh(selected_user)

    return UserPublic.model_validate(selected_user)


async def change_user_password(request: UserChangePasswordRequest, user: UserPublic, session: AsyncSession) -> UserChangePasswordResponse:
    result = await session.exec(select(User).where(User.id == user.id))
    selected_user = result.one_or_none()

    if selected_user is None:
        raise AndromedaError(404, "not_found", "Selected user not found")
    
    if not selected_user.password_hash:
        raise AndromedaError(400, "bad_request", "Password login is not set up for this account")

    if not verify_password(selected_user.password_hash, request.current_password):
        raise AndromedaError(401, "unauthorized", "Invalid password")
    
    selected_user.password_hash = hash_password(request.new_password)

    session.add(selected_user)
    await session.commit()
    
    return UserChangePasswordResponse(message="Password changed successfully")


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

    return UserPublic.model_validate(user_data)
