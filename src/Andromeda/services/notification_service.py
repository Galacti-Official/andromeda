from uuid import UUID

from fastapi import HTTPException
from sqlmodel import select, col
from sqlmodel.ext.asyncio.session import AsyncSession

from Andromeda.models.notification import Notification as NotificationModel

from Andromeda.schemas.jwt import JWTPayload

from Andromeda.schemas.notification import (
    Notification as NotificationSchema, NotificationsResponse,
    MarkReadRequest, MarkReadResponse, MarkReadAllResponse
)


async def list_notifications(user: JWTPayload, session: AsyncSession) -> NotificationsResponse:
    sub_components = user.sub.split(":")

    if sub_components[0] != "user":
        raise HTTPException(status_code=403, detail="Notifications are only accessible by user accounts.")

    user_id = UUID(sub_components[1])

    results = await session.exec(
        select(NotificationModel)
        .where(NotificationModel.user_id == user_id)
        .order_by(col(NotificationModel.created_at).desc())
        # TODO: Add pagination
    )

    notifications = [NotificationSchema.model_validate(n) for n in results]

    return NotificationsResponse(
        notifications=notifications,
        unread_count=sum(1 for n in notifications if not n.is_read)
    )
