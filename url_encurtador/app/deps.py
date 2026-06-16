from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_session

DbSession = AsyncSession


async def get_db() -> AsyncIterator[AsyncSession]:
    async for session in get_session():
        yield session
