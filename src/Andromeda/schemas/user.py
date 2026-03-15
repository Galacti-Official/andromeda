from uuid import UUID
from datetime import datetime
from pydantic import BaseModel

from Andromeda.models.user import User, UserKey


class UserPublic(BaseModel):
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
