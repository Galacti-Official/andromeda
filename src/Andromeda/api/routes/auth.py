from fastapi import APIRouter, Request, Response, Depends
from fastapi.responses import RedirectResponse
from sqlmodel.ext.asyncio.session import AsyncSession

from Andromeda.auth.external.user_auth import auth_user_key, auth_user_login, set_session_cookie, revoke_session
from Andromeda.auth.external.google_auth import auth_user_google, build_google_authorize_url, generate_oauth_state, validate_oauth_state

from Andromeda.api.database.database import get_session
from Andromeda.api.database.redis import redis_client

from Andromeda.services.user_service import create_user

from Andromeda.config import settings
from Andromeda.schemas.jwt import JWTResponse, UserTokenRequest
from Andromeda.schemas.user import UserLoginRequest, UserLoginResponse, UserLogoutResponse, UserCreateResponse, UserCreate


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/token", response_model=JWTResponse)
async def get_token(
    request: UserTokenRequest,
    session: AsyncSession = Depends(get_session)
) -> JWTResponse:
    token = await auth_user_key(request.api_key, session=session)
    return JWTResponse(access_token=str(token))


@router.post("/login", response_model=UserLoginResponse)
async def login(
    request: Request,
    response: Response,
    login_request: UserLoginRequest,
    session: AsyncSession = Depends(get_session)
) -> UserLoginResponse:
    user = await auth_user_login(login_request, session=session)
    await set_session_cookie(request, response, user, redis_client)
    return UserLoginResponse(success=True, message="User login successful", user=user)


@router.post("/register", response_model=UserCreateResponse)
async def register(
    request: Request,
    response: Response,
    register_request: UserCreate,
    session: AsyncSession = Depends(get_session)
) -> UserCreateResponse:
    user = await create_user(register_request, session=session)
    await set_session_cookie(request, response, user, redis_client)
    return UserCreateResponse(success=True, message="User created", user=user)


@router.post("/logout", response_model=UserLogoutResponse)
async def logout(
    request: Request,
    response: Response
) -> UserLogoutResponse:
    await revoke_session(request, response, redis_client)
    return UserLogoutResponse(success=True, message="User logged out successfully")


@router.get("/google/login")
async def google_login() -> RedirectResponse:
    state = await generate_oauth_state(redis_client)
    return RedirectResponse(url=build_google_authorize_url(state))


@router.get("/google/callback")
async def google_callback(
    request: Request,
    code: str,
    state: str,
    session: AsyncSession = Depends(get_session)
) -> RedirectResponse:
    await validate_oauth_state(state, redis_client)
    user = await auth_user_google(code, session)
    redirect = RedirectResponse(url=settings.frontend_url)
    await set_session_cookie(request, redirect, user, redis_client)
    return redirect
