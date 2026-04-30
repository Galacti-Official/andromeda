from sqlmodel import SQLModel, Column, DateTime, Field, text
from uuid import UUID, uuid4
from datetime import datetime, timezone


class Notification(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)

    user_id: UUID = Field(foreign_key="user.id", index=True)

    type: str = Field(max_length=32, index=True)
    title: str = Field(max_length=64)
    message: str = Field(max_length=128)

    is_read: bool = Field(default=False, index=True)

    read_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True)
    )

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    )
