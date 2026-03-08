from fastapi import APIRouter, Response, HTTPException, Depends

from Andromeda.auth.external.user_auth import auth_user_key, auth_user_login, set_session_cookie

from Andromeda.services.user_service import create_user

from Andromeda.schemas.jwt import JWTResponse, JWTPayload, UserTokenRequest
from Andromeda.schemas.user import UserLoginRequest, UserLoginResponse, UserCreateResponse, UserCreate


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/token", response_model=JWTResponse)
async def get_token(request: UserTokenRequest) -> JWTResponse:
    token = await auth_user_key(request.api_key)
    return JWTResponse(access_token=str(token))


@router.post("/login", response_model=UserLoginResponse)
async def login(request: UserLoginRequest, response: Response) -> UserLoginResponse:
    user = await auth_user_login(request)
    await set_session_cookie(response, str(user.id), ["basic"])
    return UserLoginResponse(success=True, message="User login successful", user=user)


@router.post("/register", response_model=UserCreateResponse)
async def register(request: UserCreate, response: Response) -> UserCreateResponse:
    user = await create_user(request)
    await set_session_cookie(response, str(user.id), ["basic"])
    return UserCreateResponse(success=True, message="User created", user=user)
