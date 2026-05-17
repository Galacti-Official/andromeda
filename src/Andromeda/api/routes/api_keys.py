from fastapi import APIRouter, HTTPException, Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from Andromeda.auth.dependancies import get_current_user

from Andromeda.api.database.database import get_session

from Andromeda.schemas.jwt import JWTPayload
from Andromeda.schemas.key import CreateKeyRequest, CreatedKeyResponse, DeletedKeyResponse, KeyListResponse

from Andromeda.services.api_key_service import create_api_key, delete_api_key, list_api_keys


router = APIRouter(prefix="/api-keys", tags=["api_keys"])


@router.get("/", response_model=KeyListResponse)
async def list_api_keys_request(
    user: JWTPayload = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
) -> KeyListResponse:
    return await list_api_keys(user, session)


@router.get("/{kid}", response_model=KeyListResponse)
async def get_api_key_info(
    kid: str,
    user: JWTPayload = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
) -> KeyListResponse:
    return await list_api_keys(user, session)


@router.post("/", response_model=CreatedKeyResponse)
async def request_api_key(
    request: CreateKeyRequest,
    user: JWTPayload = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
) -> CreatedKeyResponse:
    return await create_api_key(request, user, session)
    

@router.delete("/{kid}", response_model=DeletedKeyResponse)
async def delete_api_key_request(
    kid: str,
    user: JWTPayload = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
) -> DeletedKeyResponse:
    return await delete_api_key(kid, user, session)
