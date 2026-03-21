from fastapi import APIRouter, Response, Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from Andromeda.auth.external.user_auth import auth_user_key, auth_user_login, set_session_cookie

from Andromeda.api.database.database import get_session

from Andromeda.services.user_service import create_user

from Andromeda.schemas.jwt import JWTResponse, UserTokenRequest
from Andromeda.schemas.user import UserLoginRequest, UserLoginResponse, UserCreateResponse, UserCreate


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/token", response_model=JWTResponse)
async def get_token(request: UserTokenRequest, session: AsyncSession = Depends(get_session)) -> JWTResponse:
    token = await auth_user_key(request.api_key, session=session)
    return JWTResponse(access_token=str(token))


@router.post("/login", response_model=UserLoginResponse)
async def login(request: UserLoginRequest, response: Response, session: AsyncSession = Depends(get_session)) -> UserLoginResponse:
    user = await auth_user_login(request, session=session)
    set_session_cookie(response, str(user.id), ["basic"])
    return UserLoginResponse(success=True, message="User login successful", user=user)


@router.post("/register", response_model=UserCreateResponse)
async def register(request: UserCreate, response: Response, session: AsyncSession = Depends(get_session)) -> UserCreateResponse:
    user = await create_user(request, session=session)
    set_session_cookie(response, str(user.id), ["basic"])
    return UserCreateResponse(success=True, message="User created", user=user)
