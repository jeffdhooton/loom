from __future__ import annotations

import time
from typing import Callable, TypeVar

T = TypeVar("T")

_sleep = time.sleep  # module-level so tests can monkeypatch without real delays

# Transient HTTP statuses. 4xx codes other than these (401 bad key, 400 bad
# request) are permanent — retrying them just burns wall-clock before the same
# failure.
_RETRY_STATUS = frozenset({408, 409, 429, 500, 502, 503, 504})

# Connection-level failures that carry no status code. Matched by class name so
# loom does not have to import provider-specific exception hierarchies.
_RETRY_NAMES = frozenset({
    "APIConnectionError", "APITimeoutError", "APIError", "InternalServerError",
    "RateLimitError", "ConnectionError", "ConnectionResetError", "Timeout",
    "TimeoutError", "ReadTimeout", "RemoteProtocolError",
})


def is_transient(exc: BaseException) -> bool:
    status = getattr(exc, "status_code", None)
    if status is None:
        status = getattr(getattr(exc, "response", None), "status_code", None)
    if isinstance(status, int):
        return status in _RETRY_STATUS
    return type(exc).__name__ in _RETRY_NAMES


def with_retries(fn: Callable[[], T], *, attempts: int = 4, base_delay: float = 1.0,
                 on_retry: Callable[[int, float, BaseException], None] | None = None) -> T:
    """Call `fn`, retrying transient API failures with exponential backoff.

    A 429 or 5xx from the model provider used to propagate out of EXECUTE/PLAN
    and kill the whole run (`__main__` wraps the cycle in try/finally with no
    except). Retrying turns a blip into a pause instead of a dead loop.
    """
    for i in range(attempts):
        try:
            return fn()
        except Exception as e:
            if i == attempts - 1 or not is_transient(e):
                raise
            delay = base_delay * (2 ** i)
            if on_retry is not None:
                on_retry(i + 1, delay, e)
            _sleep(delay)
    raise AssertionError("unreachable")  # pragma: no cover
