from sqlmodel import SQLModel
from typing import List, Optional
from uuid import UUID, uuid4
from datetime import datetime, timezone
from pydantic import BaseModel


class CreatedKeyResponse(BaseModel):
    name: str
    type: str
    env: str
    scopes: list[str]
    key: str


class CreateKeyRequest(BaseModel):
    name: str
    type: str
    env: str
    scopes: list[str]
