import datetime as dt

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import get_cached_url, set_cached_url
from app.circuit_breaker import call_with_breaker, database_circuit_breaker
from app.db.models import Url
from app.logging_config import get_logger
from app.schemas import UrlRecord

logger = get_logger(__name__)


async def _fetch_url_from_db(session: AsyncSession, code: str) -> Url | None:
    result = await session.execute(select(Url).where(Url.code == code))
    return result.scalar_one_or_none()


async def create_url(
    session: AsyncSession,
    code: str,
    original_url: str,
    expires_at: dt.datetime | None,
) -> UrlRecord:
    url = Url(code=code, original_url=original_url, expires_at=expires_at)
    session.add(url)
    await call_with_breaker(database_circuit_breaker, session.commit)

    record = UrlRecord.model_validate(url)
    await set_cached_url(record)
    return record


async def get_url(session: AsyncSession, code: str) -> UrlRecord | None:
    cached = await get_cached_url(code)
    if cached is not None:
        logger.info("cache_hit", code=code)
        return cached

    logger.info("cache_miss", code=code)
    url = await call_with_breaker(database_circuit_breaker, _fetch_url_from_db, session, code)
    if url is None:
        return None

    record = UrlRecord.model_validate(url)
    await set_cached_url(record)
    return record
