from fastapi import HTTPException, Request, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from Andromeda.auth.external.user_auth import verify_jwt
from Andromeda.schemas.jwt import JWTPayload


security = HTTPBearer(auto_error=False)


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security)
) -> JWTPayload:
    if credentials:
        return verify_jwt(credentials.credentials)
    
    token = request.cookies.get("session")
    if token:
        return verify_jwt(token)

    raise HTTPException(status_code=401, detail="Not authenticated")


def require_scope(scope: str):
    def check_scope(user: JWTPayload = Depends(get_current_user)) -> JWTPayload:
        if user.scopes is None or scope not in user.scopes:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user
    return check_scope
