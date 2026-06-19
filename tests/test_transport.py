from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest
import requests

from ondotori_client import (
    APIError,
    AuthenticationError,
    HTTPTransport,
    RateLimitError,
    ResponseFormatError,
    RetryPolicy,
    TransportError,
)


@dataclass
class FakeResponse:
    status_code: int
    payload: Any
    headers: dict[str, str] = field(default_factory=dict)
    text: str = ""

    def json(self) -> Any:
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


class FakeSession:
    def __init__(self, outcomes: list[Any]) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[dict[str, Any]] = []
        self.closed = False

    def post(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"url": url, **kwargs})
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def close(self) -> None:
        self.closed = True


def test_successful_json_object_response() -> None:
    session = FakeSession([FakeResponse(200, {"data": []})])
    transport = HTTPTransport(session=session)

    result = transport.post_json("https://example.test", {"x": 1})

    assert result == {"data": []}
    assert session.calls[0]["json"] == {"x": 1}


def test_timeout_is_retried() -> None:
    session = FakeSession(
        [
            requests.Timeout("timeout"),
            FakeResponse(200, {"ok": True}),
        ]
    )
    sleeps: list[float] = []
    transport = HTTPTransport(
        session=session,
        retry_policy=RetryPolicy(
            max_attempts=2,
            backoff_factor=0.25,
        ),
        sleep=sleeps.append,
    )

    assert transport.post_json("https://example.test", {}) == {"ok": True}
    assert len(session.calls) == 2
    assert sleeps == [0.25]


def test_timeout_after_last_attempt_becomes_transport_error() -> None:
    session = FakeSession(
        [requests.Timeout("a"), requests.Timeout("b")]
    )
    transport = HTTPTransport(
        session=session,
        retry_policy=RetryPolicy(max_attempts=2, backoff_factor=0),
        sleep=lambda _: None,
    )

    with pytest.raises(TransportError):
        transport.post_json("https://example.test", {})


def test_authentication_error_is_not_retried() -> None:
    session = FakeSession(
        [
            FakeResponse(
                401,
                {"code": "AUTH", "message": "invalid credentials"},
            )
        ]
    )
    transport = HTTPTransport(
        session=session,
        retry_policy=RetryPolicy(max_attempts=3),
    )

    with pytest.raises(AuthenticationError) as error:
        transport.post_json("https://example.test", {})

    assert error.value.status_code == 401
    assert error.value.error_code == "AUTH"
    assert len(session.calls) == 1


def test_retryable_status_is_retried() -> None:
    session = FakeSession(
        [
            FakeResponse(503, {"message": "busy"}),
            FakeResponse(200, {"ok": True}),
        ]
    )
    transport = HTTPTransport(
        session=session,
        retry_policy=RetryPolicy(max_attempts=2, backoff_factor=0),
        sleep=lambda _: None,
    )

    assert transport.post_json("https://example.test", {}) == {"ok": True}
    assert len(session.calls) == 2


def test_rate_limit_error_contains_retry_after() -> None:
    session = FakeSession(
        [
            FakeResponse(
                429,
                {"message": "too many requests"},
                headers={"Retry-After": "3"},
            )
        ]
    )
    transport = HTTPTransport(
        session=session,
        retry_policy=RetryPolicy(max_attempts=1),
    )

    with pytest.raises(RateLimitError) as error:
        transport.post_json("https://example.test", {})

    assert error.value.retry_after == 3.0


def test_non_retryable_api_error() -> None:
    session = FakeSession([FakeResponse(400, {"message": "bad"})])
    transport = HTTPTransport(session=session)

    with pytest.raises(APIError) as error:
        transport.post_json("https://example.test", {})

    assert error.value.status_code == 400
    assert len(session.calls) == 1


def test_success_response_must_be_json_object() -> None:
    session = FakeSession([FakeResponse(200, [1, 2, 3])])
    transport = HTTPTransport(session=session)

    with pytest.raises(ResponseFormatError):
        transport.post_json("https://example.test", {})


def test_external_session_is_not_closed() -> None:
    session = FakeSession([FakeResponse(200, {})])
    transport = HTTPTransport(session=session)

    transport.close()

    assert session.closed is False
