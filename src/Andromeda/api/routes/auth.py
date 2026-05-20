from fastapi import APIRouter, Request, Response, Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from Andromeda.auth.external.user_auth import auth_user_key, auth_user_login, set_session_cookie, revoke_session

from Andromeda.api.database.database import get_session
from Andromeda.api.database.redis import redis_client

from Andromeda.services.user_service import create_user

from Andromeda.schemas.jwt import JWTResponse, UserTokenRequest
from Andromeda.schemas.user import UserLoginRequest, UserLoginResponse, UserLogoutResponse, UserCreateResponse, UserCreate


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/token", response_model=JWTResponse)
async def get_token(request: UserTokenRequest, session: AsyncSession = Depends(get_session)) -> JWTResponse:
    token = await auth_user_key(request.api_key, session=session)
    return JWTResponse(access_token=str(token))


@router.post("/login", response_model=UserLoginResponse)
async def login(request: UserLoginRequest, response: Response, session: AsyncSession = Depends(get_session)) -> UserLoginResponse:
    user = await auth_user_login(request, session=session)
    await set_session_cookie(response, user, redis_client)
    return UserLoginResponse(success=True, message="User login successful", user=user)


@router.post("/register", response_model=UserCreateResponse)
async def register(request: UserCreate, response: Response, session: AsyncSession = Depends(get_session)) -> UserCreateResponse:
    user = await create_user(request, session=session)
    await set_session_cookie(response, user, redis_client)
    return UserCreateResponse(success=True, message="User created", user=user)


@router.post("/logout", response_model=UserLogoutResponse)
async def logout(request: Request, response: Response):
    await revoke_session(request, response, redis_client)
    return UserLogoutResponse(success=True, message="User logged out successfully")
