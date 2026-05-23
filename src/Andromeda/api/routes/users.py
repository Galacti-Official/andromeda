from fastapi import APIRouter, Request, Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from Andromeda.auth.dependancies import get_session_user
from Andromeda.auth.external.user_auth import revoke_specific_session, revoke_all_sessions

from Andromeda.api.database.redis import redis_client
from Andromeda.api.database.database import get_session

from Andromeda.schemas.user import UserPublic, UserEditRequest, UserChangePasswordRequest, UserChangePasswordResponse, UserSessions

from Andromeda.services.user_service import (
    get_user_data, delete_user, edit_user, change_user_password, get_user_sessions
)

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserPublic)
async def get_me(
    user: UserPublic = Depends(get_session_user),
    session: AsyncSession = Depends(get_session)
) -> UserPublic:
    return await get_user_data(user, session)


@router.patch("/me", response_model=UserPublic)
async def edit_me(
    edit_request: UserEditRequest,
    user: UserPublic = Depends(get_session_user),
    session: AsyncSession = Depends(get_session)
) -> UserPublic:
    return await edit_user(edit_request, user, session)


@router.delete("/me", status_code=204)
async def delete_me(
    user: UserPublic = Depends(get_session_user),
    session: AsyncSession = Depends(get_session)
) -> None:
    await delete_user(user, session, redis_client)


@router.post("/me/security/change-password", response_model=UserChangePasswordResponse)
async def change_password(
    change_password_request: UserChangePasswordRequest,
    user: UserPublic = Depends(get_session_user),
    session: AsyncSession = Depends(get_session)
) -> UserChangePasswordResponse:
    return await change_user_password(change_password_request, user, session)


@router.get("/me/security/sessions")
async def get_sessions(
    request: Request,
    user: UserPublic = Depends(get_session_user)
) -> UserSessions:
    return await get_user_sessions(user, request, redis_client)


@router.delete("/me/security/sessions", status_code=204)
async def delete_sessions(
    user: UserPublic = Depends(get_session_user)
) -> None:
    await revoke_all_sessions(user, redis_client)
    

@router.delete("/me/security/sessions/{id}", status_code=204)
async def delete_session(
    id: str,
    user: UserPublic = Depends(get_session_user)
) -> None:
    await revoke_specific_session(id, user, redis_client)
