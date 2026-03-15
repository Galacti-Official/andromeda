from pydantic import BaseModel
from datetime import datetime
from uuid import UUID


class UserTokenRequest(BaseModel):
    api_key: str


class JWTResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class JWTPayload(BaseModel):
    sub: str
    scopes: list[str]
    iss: str
    aud: str
    iat: datetime
    nbf: datetime
    exp: datetime
