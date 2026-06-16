from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "url-shortener"
    environment: str = "local"
    log_level: str = "INFO"

    database_url: str = "postgresql+asyncpg://shortener:shortener@localhost:5432/shortener"

    redis_url: str = "redis://localhost:6379/0"
    cache_ttl_seconds: int = 60 * 60 * 24  # 24h

    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    snowflake_node_id: int = 1
    base_url: str = "http://localhost:8000"

    default_url_ttl_days: int = 365

    rate_limit_create: str = "10/minute"
    rate_limit_redirect: str = "60/minute"

    circuit_breaker_fail_max: int = 5
    circuit_breaker_reset_timeout: int = 30


@lru_cache
def get_settings() -> Settings:
    return Settings()
