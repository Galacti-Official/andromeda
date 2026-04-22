from fastapi import APIRouter, Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from Andromeda.auth.dependancies import get_current_user

from Andromeda.api.database.database import get_session

from Andromeda.services.notification_service import list_notifications

from Andromeda.schemas.jwt import JWTPayload
from Andromeda.schemas.notification import NotificationsResponse


router = APIRouter(prefix="/notifications", tags=["dashboard", "notifications"])


@router.get("/", response_model=NotificationsResponse)
async def get_notifications(
    user: JWTPayload = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    return await list_notifications(user, session)
