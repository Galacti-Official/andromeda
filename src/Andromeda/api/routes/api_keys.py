from fastapi import APIRouter, HTTPException, Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from Andromeda.auth.dependancies import get_current_user

from Andromeda.api.database.database import get_session

from Andromeda.schemas.jwt import JWTPayload
from Andromeda.schemas.key import CreateKeyRequest, CreatedKeyResponse

from Andromeda.services.api_key_service import create_api_key


router = APIRouter(prefix="/api-keys", tags=["api_keys"])


@router.post("/", response_model=CreatedKeyResponse)
async def request_api_key(
    request: CreateKeyRequest,
    user: JWTPayload = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
) -> CreatedKeyResponse | None:
    try:
        return await create_api_key(request, user, session)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
