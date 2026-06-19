from __future__ import annotations

import logging
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from types import TracebackType
from typing import Any, Final, TypeAlias

import requests

from .exceptions import (
    APIError,
    AuthenticationError,
    RateLimitError,
    ResponseFormatError,
    TransportError,
)

JsonObject: TypeAlias = dict[str, Any]
Timeout: TypeAlias = float | tuple[float, float]

_DEFAULT_RETRY_STATUS_CODES: Final[frozenset[int]] = frozenset(
    {408, 429, 500, 502, 503, 504}
)
_AUTHENTICATION_STATUS_CODES: Final[frozenset[int]] = frozenset({401, 403})
_MAX_RESPONSE_BODY_LENGTH: Final[int] = 2_000
_LOGGER = logging.getLogger(__name__)


def _validate_positive_number(
    value: float,
    *,
    field_name: str,
    allow_zero: bool = False,
) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} には数値を指定してください")
    try:
        normalized = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} には数値を指定してください") from exc

    if allow_zero:
        if normalized < 0:
            raise ValueError(f"{field_name} は0以上である必要があります")
    elif normalized <= 0:
        raise ValueError(f"{field_name} は正の値である必要があります")
    return normalized


def _validate_timeout(timeout: Timeout) -> Timeout:
    if isinstance(timeout, tuple):
        if len(timeout) != 2:
            raise ValueError(
                "timeout のタプルは "
                "(接続タイムアウト, 読み込みタイムアウト) の2要素で"
                "指定してください"
            )
        return (
            _validate_positive_number(
                timeout[0],
                field_name="接続タイムアウト",
            ),
            _validate_positive_number(
                timeout[1],
                field_name="読み込みタイムアウト",
            ),
        )
    return _validate_positive_number(timeout, field_name="timeout")


def _truncate_response_body(text: str) -> str:
    if len(text) <= _MAX_RESPONSE_BODY_LENGTH:
        return text
    omitted_length = len(text) - _MAX_RESPONSE_BODY_LENGTH
    return (
        text[:_MAX_RESPONSE_BODY_LENGTH]
        + f"\n... ({omitted_length} characters omitted)"
    )


def _response_body(response: requests.Response) -> str | None:
    try:
        text = response.text
    except Exception:
        return None
    if not text:
        return None
    return _truncate_response_body(text)


def _extract_error_information(
    response: requests.Response,
) -> tuple[str | int | None, str | None, dict[str, Any]]:
    try:
        payload = response.json()
    except ValueError:
        return None, None, {}

    if not isinstance(payload, Mapping):
        return None, None, {"response_json": payload}

    payload_dict = dict(payload)
    error_code: str | int | None = None
    message: str | None = None

    for key in ("error_code", "error-code", "code", "status"):
        value = payload_dict.get(key)
        if isinstance(value, (str, int)) and not isinstance(value, bool):
            error_code = value
            break

    for key in (
        "message",
        "error_message",
        "error-message",
        "error",
        "detail",
        "description",
    ):
        value = payload_dict.get(key)
        if isinstance(value, str) and value.strip():
            message = value.strip()
            break

    return error_code, message, payload_dict


def _parse_retry_after(response: requests.Response) -> float | None:
    raw_value = response.headers.get("Retry-After")
    if raw_value is None:
        return None

    normalized = raw_value.strip()
    if not normalized:
        return None

    try:
        return max(0.0, float(normalized))
    except ValueError:
        pass

    try:
        retry_datetime = parsedate_to_datetime(normalized)
    except (TypeError, ValueError, OverflowError):
        return None

    if retry_datetime.tzinfo is None:
        retry_datetime = retry_datetime.replace(tzinfo=timezone.utc)
    return max(
        0.0,
        (
            retry_datetime.astimezone(timezone.utc) - datetime.now(timezone.utc)
        ).total_seconds(),
    )


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """HTTP リトライ方針．max_attempts は初回を含む試行回数．"""

    max_attempts: int = 3
    backoff_factor: float = 0.5
    max_backoff: float = 10.0
    retry_status_codes: frozenset[int] = _DEFAULT_RETRY_STATUS_CODES
    respect_retry_after: bool = True

    def __post_init__(self) -> None:
        if isinstance(self.max_attempts, bool) or not isinstance(
            self.max_attempts,
            int,
        ):
            raise ValueError("max_attempts には整数を指定してください")
        if self.max_attempts < 1:
            raise ValueError("max_attempts は1以上である必要があります")

        normalized_backoff_factor = _validate_positive_number(
            self.backoff_factor,
            field_name="backoff_factor",
            allow_zero=True,
        )
        normalized_max_backoff = _validate_positive_number(
            self.max_backoff,
            field_name="max_backoff",
            allow_zero=True,
        )

        normalized_status_codes: set[int] = set()
        for status_code in self.retry_status_codes:
            if (
                isinstance(status_code, bool)
                or not isinstance(status_code, int)
                or not 100 <= status_code <= 599
            ):
                raise ValueError(
                    "retry_status_codes には有効な HTTP ステータスコードを"
                    "指定してください"
                )
            normalized_status_codes.add(status_code)

        object.__setattr__(
            self,
            "backoff_factor",
            normalized_backoff_factor,
        )
        object.__setattr__(self, "max_backoff", normalized_max_backoff)
        object.__setattr__(
            self,
            "retry_status_codes",
            frozenset(normalized_status_codes),
        )

    def should_retry_status(self, status_code: int) -> bool:
        return status_code in self.retry_status_codes

    def get_backoff_seconds(
        self,
        *,
        failed_attempt: int,
        retry_after: float | None = None,
    ) -> float:
        exponential_backoff = self.backoff_factor * (
            2 ** max(0, failed_attempt - 1)
        )
        wait_seconds = min(exponential_backoff, self.max_backoff)
        if self.respect_retry_after and retry_after is not None:
            wait_seconds = min(
                max(wait_seconds, retry_after),
                self.max_backoff,
            )
        return float(wait_seconds)


class HTTPTransport:
    """Ondotori WebStorage API との HTTP 通信を担当する．"""

    def __init__(
        self,
        *,
        timeout: Timeout = 10.0,
        retry_policy: RetryPolicy | None = None,
        session: requests.Session | None = None,
        logger: logging.Logger | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.timeout = _validate_timeout(timeout)
        self.retry_policy = retry_policy or RetryPolicy()
        self._logger = logger or _LOGGER
        self._sleep = sleep

        if session is None:
            self.session = requests.Session()
            self._owns_session = True
        else:
            self.session = session
            self._owns_session = False
        self._closed = False

    def post_json(
        self,
        url: str,
        payload: Mapping[str, Any],
        *,
        headers: Mapping[str, str] | None = None,
    ) -> JsonObject:
        if self._closed:
            raise RuntimeError("HTTPTransport は既に閉じられています")
        if not isinstance(url, str) or not url.strip():
            raise ValueError("url には空でない文字列を指定してください")
        if not isinstance(payload, Mapping):
            raise TypeError("payload には Mapping を指定してください")

        normalized_headers = dict(headers or {})
        last_transport_error: requests.RequestException | None = None
        last_response: requests.Response | None = None

        for attempt in range(1, self.retry_policy.max_attempts + 1):
            self._logger.debug(
                "POST %s attempt=%d/%d",
                url,
                attempt,
                self.retry_policy.max_attempts,
            )
            try:
                response = self.session.post(
                    url,
                    json=dict(payload),
                    headers=normalized_headers,
                    timeout=self.timeout,
                )
            except (requests.Timeout, requests.ConnectionError) as exc:
                last_transport_error = exc
                if attempt >= self.retry_policy.max_attempts:
                    raise TransportError(
                        "Ondotori WebStorage API への通信に失敗しました"
                    ) from exc

                wait_seconds = self.retry_policy.get_backoff_seconds(
                    failed_attempt=attempt
                )
                self._logger.warning(
                    "HTTP communication failed; retrying: "
                    "url=%s attempt=%d/%d wait=%.3fs error=%s",
                    url,
                    attempt,
                    self.retry_policy.max_attempts,
                    wait_seconds,
                    type(exc).__name__,
                )
                self._sleep(wait_seconds)
                continue
            except requests.RequestException as exc:
                raise TransportError(
                    "HTTP リクエストを実行できませんでした"
                ) from exc

            last_response = response
            if 200 <= response.status_code < 300:
                return self._decode_success_response(response, url=url)

            if response.status_code in _AUTHENTICATION_STATUS_CODES:
                raise self._authentication_error(response, url=url)

            if self.retry_policy.should_retry_status(response.status_code):
                retry_after = _parse_retry_after(response)
                if attempt >= self.retry_policy.max_attempts:
                    raise self._api_error_from_response(
                        response,
                        url=url,
                        retry_after=retry_after,
                    )

                wait_seconds = self.retry_policy.get_backoff_seconds(
                    failed_attempt=attempt,
                    retry_after=retry_after,
                )
                self._logger.warning(
                    "Retryable API response; retrying: "
                    "url=%s status=%d attempt=%d/%d wait=%.3fs",
                    url,
                    response.status_code,
                    attempt,
                    self.retry_policy.max_attempts,
                    wait_seconds,
                )
                self._sleep(wait_seconds)
                continue

            raise self._api_error_from_response(response, url=url)

        if last_response is not None:
            raise self._api_error_from_response(last_response, url=url)
        if last_transport_error is not None:
            raise TransportError(
                "Ondotori WebStorage API への通信に失敗しました"
            ) from last_transport_error
        raise RuntimeError(
            "HTTPTransport.post_json が予期しない状態で終了しました"
        )

    @staticmethod
    def _decode_success_response(
        response: requests.Response,
        *,
        url: str,
    ) -> JsonObject:
        try:
            payload = response.json()
        except ValueError as exc:
            raise ResponseFormatError(
                "API の成功応答を JSON として解析できませんでした",
                url=url,
                response_body=_response_body(response),
            ) from exc

        if not isinstance(payload, Mapping):
            raise ResponseFormatError(
                "API の成功応答が JSON オブジェクトではありません",
                url=url,
                response_body=_response_body(response),
            )
        return dict(payload)

    @staticmethod
    def _authentication_error(
        response: requests.Response,
        *,
        url: str,
    ) -> AuthenticationError:
        error_code, api_message, details = _extract_error_information(response)
        return AuthenticationError(
            api_message or "Ondotori WebStorage API の認証に失敗しました",
            status_code=response.status_code,
            url=url,
            response_body=_response_body(response),
            error_code=error_code,
            details=details,
        )

    @staticmethod
    def _api_error_from_response(
        response: requests.Response,
        *,
        url: str,
        retry_after: float | None = None,
    ) -> APIError:
        error_code, api_message, details = _extract_error_information(response)
        if response.status_code == 429:
            return RateLimitError(
                api_message
                or "Ondotori WebStorage API のレート制限に達しました",
                retry_after=retry_after,
                status_code=response.status_code,
                url=url,
                response_body=_response_body(response),
                error_code=error_code,
                details=details,
            )

        return APIError(
            api_message
            or (
                "Ondotori WebStorage API がエラー応答を返しました: "
                f"HTTP {response.status_code}"
            ),
            status_code=response.status_code,
            url=url,
            response_body=_response_body(response),
            error_code=error_code,
            details=details,
        )

    def close(self) -> None:
        if self._closed:
            return
        if self._owns_session:
            self.session.close()
        self._closed = True

    def __enter__(self) -> HTTPTransport:
        if self._closed:
            raise RuntimeError("閉じられた HTTPTransport は再利用できません")
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()


__all__ = ["HTTPTransport", "JsonObject", "RetryPolicy", "Timeout"]
