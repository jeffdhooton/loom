import pytest

from setpoint import retry
from setpoint.retry import is_transient, with_retries


class _Status(Exception):
    def __init__(self, status_code):
        super().__init__(f"status {status_code}")
        self.status_code = status_code


class RateLimitError(Exception):
    """Name-matched transient (no status attribute), like the openai class."""


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    slept = []
    monkeypatch.setattr(retry, "_sleep", slept.append)
    return slept


def test_transient_statuses_retry():
    assert is_transient(_Status(429))
    assert is_transient(_Status(503))


def test_permanent_statuses_do_not_retry():
    assert not is_transient(_Status(401))
    assert not is_transient(_Status(400))


def test_transient_by_class_name():
    assert is_transient(RateLimitError())
    assert not is_transient(ValueError("nope"))


def test_retries_then_succeeds(_no_sleep):
    calls = []

    def fn():
        calls.append(1)
        if len(calls) < 3:
            raise _Status(429)
        return "ok"

    assert with_retries(fn) == "ok"
    assert len(calls) == 3
    assert _no_sleep == [1.0, 2.0]  # exponential backoff


def test_permanent_error_raises_immediately(_no_sleep):
    calls = []

    def fn():
        calls.append(1)
        raise _Status(401)

    with pytest.raises(_Status):
        with_retries(fn)
    assert len(calls) == 1  # no retry burned on a bad API key
    assert _no_sleep == []


def test_gives_up_after_attempts(_no_sleep):
    calls = []

    def fn():
        calls.append(1)
        raise _Status(500)

    with pytest.raises(_Status):
        with_retries(fn, attempts=3)
    assert len(calls) == 3


def test_on_retry_callback_receives_attempt_and_delay(_no_sleep):
    seen = []

    def fn():
        if len(seen) < 1:
            raise _Status(502)
        return "done"

    with_retries(fn, on_retry=lambda n, delay, e: seen.append((n, delay)))
    assert seen == [(1, 1.0)]
