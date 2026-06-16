import datetime as dt
from typing import Any, Awaitable, Callable, TypeVar

import pybreaker

from app.config import get_settings
from app.logging_config import get_logger

logger = get_logger(__name__)
settings = get_settings()

T = TypeVar("T")


class StructlogBreakerListener(pybreaker.CircuitBreakerListener):
    def state_change(self, cb, old_state, new_state):
        logger.warning(
            "circuit_breaker_state_change",
            breaker=cb.name,
            old_state=old_state.name,
            new_state=new_state.name,
        )

    def failure(self, cb, exc):
        logger.error("circuit_breaker_failure", breaker=cb.name, error=str(exc))


database_circuit_breaker = pybreaker.CircuitBreaker(
    fail_max=settings.circuit_breaker_fail_max,
    reset_timeout=settings.circuit_breaker_reset_timeout,
    name="database",
    listeners=[StructlogBreakerListener()],
)


async def call_with_breaker(
    breaker: pybreaker.CircuitBreaker,
    func: Callable[..., Awaitable[T]],
    *args: Any,
    **kwargs: Any,
) -> T:
    """Run an async callable guarded by a pybreaker CircuitBreaker.

    pybreaker's own ``call_async`` is broken in this version (it references
    Tornado's ``gen`` module without importing it), so we replicate its
    before/success/error bookkeeping directly using the documented state hooks,
    without delegating to the sync-only ``before_call``/``call`` path (which
    would call our coroutine function synchronously and return un-awaited).
    """
    if isinstance(breaker.state, pybreaker.CircuitOpenState):
        timeout = dt.timedelta(seconds=breaker.reset_timeout)
        opened_at = breaker._state_storage.opened_at
        if opened_at and dt.datetime.now(dt.timezone.utc) < opened_at + timeout:
            raise pybreaker.CircuitBreakerError("Timeout not elapsed yet, circuit breaker still open")
        breaker.half_open()

    state = breaker.state
    try:
        result = await func(*args, **kwargs)
    except BaseException as exc:
        state._handle_error(exc)
        raise
    else:
        state._handle_success()
        return result
