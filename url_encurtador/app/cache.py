from redis.asyncio import Redis, from_url

from app.config import get_settings
from app.schemas import UrlRecord

settings = get_settings()

_redis: Redis | None = None


def get_redis() -> Redis:
    global _redis
    if _redis is None:
        _redis = from_url(settings.redis_url, decode_responses=True)
    return _redis


def _cache_key(code: str) -> str:
    return f"url:{code}"


async def get_cached_url(code: str) -> UrlRecord | None:
    redis = get_redis()
    raw = await redis.get(_cache_key(code))
    if raw is None:
        return None
    return UrlRecord.model_validate_json(raw)


async def set_cached_url(record: UrlRecord, ttl_seconds: int | None = None) -> None:
    redis = get_redis()
    ttl = ttl_seconds if ttl_seconds is not None else settings.cache_ttl_seconds
    await redis.set(_cache_key(record.code), record.model_dump_json(), ex=ttl)


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.close()
        _redis = None
