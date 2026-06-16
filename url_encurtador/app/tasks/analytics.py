import datetime as dt

from app.logging_config import configure_logging, get_logger
from app.tasks.celery_app import celery_app

configure_logging()
logger = get_logger(__name__)


@celery_app.task(name="app.tasks.analytics.log_click")
def log_click(code: str, timestamp: str, user_agent: str | None) -> None:
    logger.info(
        "click_logged",
        code=code,
        timestamp=timestamp,
        user_agent=user_agent,
    )


def enqueue_click(code: str, user_agent: str | None) -> None:
    log_click.delay(
        code=code,
        timestamp=dt.datetime.now(dt.timezone.utc).isoformat(),
        user_agent=user_agent,
    )
