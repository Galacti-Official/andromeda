from fastapi import APIRouter, HTTPException, Depends

from Andromeda.auth.external.user_auth import auth_user_key
from Andromeda.auth.dependancies import get_current_user
from Andromeda.schemas.jwt import JWTPayload
from Andromeda.schemas.key import CreateKeyRequest, CreatedKeyResponse
from Andromeda.services.api_key_service import create_api_key


router = APIRouter(prefix="/api-keys", tags=["api_keys"])


@router.post("/", response_model=CreatedKeyResponse)
async def request_api_key(request: CreateKeyRequest, user: JWTPayload = Depends(get_current_user)):
    try:
        return await create_api_key(request, user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
