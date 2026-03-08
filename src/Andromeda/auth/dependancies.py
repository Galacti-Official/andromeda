from typing import Optional

from fastapi import HTTPException, Request, Cookie, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt

from Andromeda.auth.external.user_auth import verify_jwt
from Andromeda.schemas.jwt import JWTPayload


security = HTTPBearer(auto_error=False)


async def get_current_user(request: Request, credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> Optional[JWTPayload]:
    if credentials:
        return await verify_jwt(credentials.credentials)
    
    token = request.cookies.get("access_token")
    if token:
        return await verify_jwt(token)

    raise HTTPException(status_code=401, detail="Not authenticated")


def require_scope(scope: str):
    async def check_scope(user: JWTPayload = Depends(get_current_user)) -> JWTPayload:
        if user.scopes is None or scope not in user.scopes:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user
    return check_scope
