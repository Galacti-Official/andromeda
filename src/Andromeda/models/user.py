from sqlmodel import SQLModel, Field, Relationship, JSON
from sqlalchemy import Column, DateTime
from typing import List, Optional
from uuid import UUID, uuid4
from datetime import datetime, timezone


class User(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)

    name: str = Field(index=True)
    email: str = Field(unique=True, index=True)
    password_hash: str

    email_verified: bool | None = Field(default=False)

    has_2FA_auth: bool | None = Field(default=False)
    
    is_active: bool | None = Field(default=True)

    keys: List["UserKey"] = Relationship(back_populates="user")

    avatar: str = Field(default="https://cdn.galacti.org/avatars/default.png")

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )

    last_login: datetime | None = Field(
        sa_column=Column(DateTime(timezone=True), nullable=True)
    )


class UserKey(SQLModel, table=True):
    id: UUID | None = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)

    name: str | None
    kid: str = Field(index=True, unique=True)

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    
    secret_hash: str
    is_active: bool | None = Field(default=True)

    scopes: Optional[list[str]] = Field(default=None, sa_column=Column(JSON, nullable=True))

    user: Optional["User"] = Relationship(back_populates="keys")
