from pydantic import BaseModel
from uuid import UUID
from datetime import datetime


class Notification(BaseModel):
    id: UUID
    type: str
    
    title: str
    message: str
    
    is_read: bool

    read_at: datetime | None
    created_at: datetime


class NotificationsResponse(BaseModel):
    notifications: list[Notification]
    unread_count: int


class MarkReadRequest(BaseModel):
    ids: list[UUID]


class MarkReadResponse(BaseModel):
    success: bool
    marked_read: list[UUID]


class MarkReadAllResponse(BaseModel):
    success: bool
    marked_read_count: int
