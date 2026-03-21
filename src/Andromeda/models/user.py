from sqlmodel import SQLModel, Column, DateTime, JSON, Field, Relationship, text
from typing import Optional
from uuid import UUID, uuid4
from datetime import datetime, timezone


class User(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)

    name: str = Field(index=True, max_length=64)
    email: str = Field(unique=True, index=True)
    password_hash: str

    email_verified: bool = Field(default=False)

    has_2fa_auth: bool = Field(default=False)
    
    is_active: bool = Field(default=True)

    keys: list["UserKey"] = Relationship(back_populates="user")

    avatar: str = Field(default="https://cdn.galacti.org/avatars/default.png")

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    )

    last_login: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True)
    )


class UserKey(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)

    name: str | None = Field(default=None, index=True, max_length=128)
    kid: str = Field(index=True, unique=True, max_length=22)

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    )
    
    secret_hash: str
    is_active: bool = Field(default=True)

    scopes: list[str] | None = Field(default=None, sa_column=Column(JSON, nullable=True))

    user: Optional["User"] = Relationship(back_populates="keys")
