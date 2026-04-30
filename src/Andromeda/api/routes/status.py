from fastapi import APIRouter, Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from Andromeda.api.database.database import get_session
from Andromeda.services.status_service import get_status as get_status_service
from Andromeda.schemas.status import StatusResponse

router = APIRouter(prefix="/status", tags=["status"])

@router.get("/", response_model=StatusResponse)
async def get_status(session: AsyncSession = Depends(get_session)):
    return await get_status_service(session)
