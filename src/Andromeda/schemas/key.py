from pydantic import BaseModel, ConfigDict
from datetime import datetime


class CreateKeyRequest(BaseModel):
    name: str
    type: str
    env: str
    scopes: list[str]


class CreatedKeyResponse(BaseModel):
    name: str
    type: str
    env: str
    scopes: list[str] | None
    key: str


class DeletedKeyResponse(BaseModel):
    message: str


class ActivatedKeyResponse(BaseModel):
    message: str


class DeactivatedKeyResponse(BaseModel):
    message: str


class EditKeyRequest(BaseModel):
    name: str | None
    scopes: list[str] | None


class KeyPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    kid: str
    scopes: list[str]
    last_used: datetime | None
    created_at: datetime
    is_active: bool


class KeySpecific(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    kid: str
    scopes: list[str] | None
    created_at: datetime
    is_active: bool
    last_used: datetime | None
    calls_today: int = 0
    calls_this_hour: int = 0
    

class KeyListResponse(BaseModel):
    keys: list[KeyPublic]
