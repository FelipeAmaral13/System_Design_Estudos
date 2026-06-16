import datetime as dt

import pybreaker
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app import repository
from app.base62 import encode
from app.config import get_settings
from app.deps import get_db
from app.limiter import limiter
from app.logging_config import get_logger
from app.schemas import UrlCreateRequest, UrlCreateResponse
from app.snowflake import SnowflakeGenerator
from app.tasks.analytics import enqueue_click

router = APIRouter()
logger = get_logger(__name__)
settings = get_settings()

_snowflake = SnowflakeGenerator(node_id=settings.snowflake_node_id)


@router.post("/urls", response_model=UrlCreateResponse, status_code=201)
@limiter.limit(settings.rate_limit_create)
async def create_short_url(
    payload: UrlCreateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> UrlCreateResponse:
    code = encode(_snowflake.next_id())
    ttl_days = payload.ttl_days if payload.ttl_days is not None else settings.default_url_ttl_days
    expires_at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=ttl_days)

    try:
        record = await repository.create_url(
            session=db,
            code=code,
            original_url=str(payload.original_url),
            expires_at=expires_at,
        )
    except pybreaker.CircuitBreakerError:
        logger.error("circuit_open_on_create", code=code)
        raise HTTPException(status_code=503, detail="Database temporarily unavailable")
    except SQLAlchemyError:
        logger.exception("db_error_on_create", code=code)
        raise HTTPException(status_code=500, detail="Failed to create short URL")

    return UrlCreateResponse(
        code=record.code,
        short_url=f"{settings.base_url}/{record.code}",
        original_url=record.original_url,
        created_at=record.created_at,
        expires_at=record.expires_at,
    )


@router.get("/{code}")
@limiter.limit(settings.rate_limit_redirect)
async def redirect_to_original(
    code: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    try:
        record = await repository.get_url(db, code)
    except pybreaker.CircuitBreakerError:
        logger.error("circuit_open_on_redirect", code=code)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")
    except SQLAlchemyError:
        logger.exception("db_error_on_redirect", code=code)
        raise HTTPException(status_code=500, detail="Failed to resolve short URL")

    if record is None:
        raise HTTPException(status_code=404, detail="Short URL not found")

    if record.expires_at is not None and record.expires_at < dt.datetime.now(dt.timezone.utc):
        raise HTTPException(status_code=410, detail="Short URL has expired")

    enqueue_click(code=code, user_agent=request.headers.get("user-agent"))

    return RedirectResponse(url=record.original_url, status_code=307)
