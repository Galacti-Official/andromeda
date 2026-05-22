from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    email: str
    avatar: str
    last_login: datetime | None
    created_at: datetime


class UserCreate(BaseModel):
    name: str
    email: str
    password: str


class UserCreateResponse(BaseModel):
    success: bool
    message: str
    user: UserPublic


class UserLoginRequest(BaseModel):
    email: str
    password: str


class UserLoginResponse(BaseModel):
    success: bool
    message: str
    user: UserPublic


class UserLogoutResponse(BaseModel):
    success: bool
    message: str


class UserSession(BaseModel):
    session_id: str
    is_current_session: bool
    created_at: datetime
    last_used_at: datetime
    browser: str
    os: str
    device_type: str


class UserSessions(BaseModel):
    sessions: list[UserSession]
