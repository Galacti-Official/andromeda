from fastapi import APIRouter, Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from Andromeda.auth.dependancies import get_session_user

from Andromeda.api.database.database import get_session

from Andromeda.schemas.user import UserPublic

from Andromeda.schemas.key import (
    CreateKeyRequest, CreatedKeyResponse, DeletedKeyResponse, ActivatedKeyResponse, DeactivatedKeyResponse,
    KeyListResponse, KeySpecific, EditKeyRequest
)

from Andromeda.services.api_key_service import (
    create_api_key, delete_api_key, activate_api_key, deactivate_api_key,
    list_api_keys, get_api_key_info, edit_api_key, regenerate_api_key
)


router = APIRouter(prefix="/api-keys", tags=["api_keys"])


@router.get("/", response_model=KeyListResponse)
async def list_api_keys_request(
    user: UserPublic = Depends(get_session_user),
    session: AsyncSession = Depends(get_session)
) -> KeyListResponse:
    return await list_api_keys(user, session)


@router.get("/{kid}", response_model=KeySpecific)
async def api_key_info_request(
    kid: str,
    user: UserPublic = Depends(get_session_user),
    session: AsyncSession = Depends(get_session)
) -> KeySpecific:
    return await get_api_key_info(kid, user, session)


@router.delete("/{kid}", response_model=DeletedKeyResponse)
async def delete_api_key_request(
    kid: str,
    user: UserPublic = Depends(get_session_user),
    session: AsyncSession = Depends(get_session)
) -> DeletedKeyResponse:
    return await delete_api_key(kid, user, session)


@router.post("/", response_model=CreatedKeyResponse)
async def request_api_key(
    request: CreateKeyRequest,
    user: UserPublic = Depends(get_session_user),
    session: AsyncSession = Depends(get_session)
) -> CreatedKeyResponse:
    return await create_api_key(request, user, session)
    

@router.post("/{kid}/activate", response_model=ActivatedKeyResponse)
async def activate_api_key_request(
    kid: str,
    user: UserPublic = Depends(get_session_user),
    session: AsyncSession = Depends(get_session)
) -> ActivatedKeyResponse:
    return await activate_api_key(kid, user, session)


@router.post("/{kid}/deactivate", response_model=DeactivatedKeyResponse)
async def deactivate_api_key_request(
    kid: str,
    user: UserPublic = Depends(get_session_user),
    session: AsyncSession = Depends(get_session)
) -> DeactivatedKeyResponse:
    return await deactivate_api_key(kid, user, session)


@router.post("/{kid}/regenerate", response_model=CreatedKeyResponse)
async def regenerate_api_key_request(
    kid: str,
    user: UserPublic = Depends(get_session_user),
    session: AsyncSession = Depends(get_session)
) -> CreatedKeyResponse:
    return await regenerate_api_key(kid, user, session)


@router.patch("/{kid}", response_model=KeySpecific)
async def edit_api_key_request(
    kid: str,
    request: EditKeyRequest,
    user: UserPublic = Depends(get_session_user),
    session: AsyncSession = Depends(get_session)
) -> KeySpecific:
    return await edit_api_key(kid, user, request, session)
