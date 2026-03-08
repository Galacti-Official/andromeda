from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio.session import async_sessionmaker

from Andromeda.config import settings


DATABASE_URL = settings.database_url

engine: AsyncEngine = create_async_engine(DATABASE_URL, echo=True, pool_pre_ping=True)

async_session = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


@asynccontextmanager
async def get_session():
    async with async_session() as session:
        yield session