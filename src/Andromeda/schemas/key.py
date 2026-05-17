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
    scopes: list[str]
    key: str


class DeletedKeyResponse(BaseModel):
    message: str


class KeyPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    name: str
    kid: str
    scopes: list[str]
    last_used: datetime | None
    created_at: datetime
    is_active: bool


class KeyCallDay(BaseModel):
    date: datetime
    calls: int


class KeyUsage(BaseModel):
    error_rate: int
    daily_usage: list[KeyCallDay]
    

class KeySpecific(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    name: str
    kid: str
    scopes: list[str]
    last_used: datetime | None
    created_at: datetime
    is_active: bool
    usage: KeyUsage
    

class KeyListResponse(BaseModel):
    keys: list[KeyPublic]
