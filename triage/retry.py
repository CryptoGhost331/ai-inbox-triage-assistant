"""Retry with exponential backoff and jitter.

The same pattern used for exchange-API reconnects: transient failures
(timeouts, rate limits, 5xx) are retried with growing waits; anything else
fails fast so it can be logged and alerted.
"""

from __future__ import annotations

import functools
import random
import time
from typing import Callable, TypeVar

T = TypeVar("T")


class TransientError(Exception):
    """A failure worth retrying (timeout, rate limit, server error)."""


def with_retries(
    attempts: int = 4,
    base_delay: float = 1.0,
    max_delay: float = 20.0,
    sleep: Callable[[float], None] = time.sleep,
    on_retry: Callable[[int, Exception, float], None] | None = None,
):
    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs) -> T:
            for attempt in range(1, attempts + 1):
                try:
                    return fn(*args, **kwargs)
                except TransientError as exc:
                    if attempt == attempts:
                        raise
                    delay = min(max_delay, base_delay * 2 ** (attempt - 1))
                    delay += random.uniform(0, delay * 0.25)
                    if on_retry:
                        on_retry(attempt, exc, delay)
                    sleep(delay)
            raise RuntimeError("unreachable")

        return wrapper

    return decorator
