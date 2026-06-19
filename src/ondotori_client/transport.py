# 保存先:
# src/ondotori_client/transport.py
#
# HTTP通信，タイムアウト，リトライ，エラー応答の変換を担当する
# モジュールです．
#
# 認証情報を含むリクエスト payload はログへ出力しません．

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
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
    {
        408,  # Request Timeout
        429,  # Too Many Requests
        500,  # Internal Server Error
        502,  # Bad Gateway
        503,  # Service Unavailable
        504,  # Gateway Timeout
    }
)

_AUTHENTICATION_STATUS_CODES: Final[frozenset[int]] = frozenset(
    {
        401,  # Unauthorized
        403,  # Forbidden
    }
)

_MAX_RESPONSE_BODY_LENGTH: Final[int] = 2_000

logger = logging.getLogger(__name__)


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
        raise ValueError(
            f"{field_name} には数値を指定してください"
        ) from exc

    if allow_zero:
        if normalized < 0:
            raise ValueError(
                f"{field_name} は0以上である必要があります"
            )
    elif normalized <= 0:
        raise ValueError(
            f"{field_name} は正の値である必要があります"
        )

    return normalized


def _validate_timeout(timeout: Timeout) -> Timeout:
    """
    requests が受け付けるタイムアウト値を検証する．

    float:
        接続と読み込みの両方に同じ秒数を使用する．

    tuple[float, float]:
        (接続タイムアウト, 読み込みタイムアウト)．
    """
    if isinstance(timeout, tuple):
        if len(timeout) != 2:
            raise ValueError(
                "timeout のタプルは "
                "(接続タイムアウト, 読み込みタイムアウト) "
                "の2要素で指定してください"
            )

        connect_timeout = _validate_positive_number(
            timeout[0],
            field_name="接続タイムアウト",
        )
        read_timeout = _validate_positive_number(
            timeout[1],
            field_name="読み込みタイムアウト",
        )

        return connect_timeout, read_timeout

    return _validate_positive_number(
        timeout,
        field_name="timeout",
    )


def _truncate_response_body(text: str) -> str:
    """
    例外に保持するレスポンス本文を過度に長くしないよう切り詰める．
    """
    if len(text) <= _MAX_RESPONSE_BODY_LENGTH:
        return text

    omitted_length = len(text) - _MAX_RESPONSE_BODY_LENGTH

    return (
        text[:_MAX_RESPONSE_BODY_LENGTH]
        + f"\n... ({omitted_length} characters omitted)"
    )


def _response_body(response: requests.Response) -> str | None:
    """
    レスポンス本文を安全に取得する．
    """
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
    """
    API の JSON エラー応答から，エラーコードとメッセージを抽出する．

    API の厳密なエラー形式に依存しすぎないよう，複数の一般的な
    キー名を順番に確認する．
    """
    try:
        payload = response.json()
    except (requests.JSONDecodeError, ValueError):
        return None, None, {}

    if not isinstance(payload, Mapping):
        return None, None, {"response_json": payload}

    payload_dict = dict(payload)

    error_code: str | int | None = None
    message: str | None = None

    for key in (
        "error_code",
        "error-code",
        "code",
        "status",
    ):
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


def _parse_retry_after(
    response: requests.Response,
) -> float | None:
    """
    Retry-After ヘッダーを待機秒数へ変換する．

    Retry-After は以下のいずれかで指定される．

    - 秒数
    - HTTP-date
    """
    raw_value = response.headers.get("Retry-After")

    if raw_value is None:
        return None

    normalized = raw_value.strip()

    if not normalized:
        return None

    try:
        seconds = float(normalized)
    except ValueError:
        seconds = None

    if seconds is not None:
        return max(0.0, seconds)

    try:
        retry_datetime = parsedate_to_datetime(normalized)
    except (TypeError, ValueError, OverflowError):
        return None

    if retry_datetime.tzinfo is None:
        retry_datetime = retry_datetime.replace(tzinfo=UTC)

    current_datetime = datetime.now(UTC)

    return max(
        0.0,
        (retry_datetime.astimezone(UTC) - current_datetime).total_seconds(),
    )


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """
    HTTP リトライ方針．

    Attributes:
        max_attempts:
            初回リクエストを含む最大試行回数．
            3の場合，初回1回と再試行最大2回になる．
        backoff_factor:
            指数バックオフの基準秒数．
            待機時間は概ね
            backoff_factor * 2 ** (attempt - 1)
            で計算する．
        max_backoff:
            バックオフ時間の上限秒数．
        retry_status_codes:
            再試行対象の HTTP ステータスコード．
        respect_retry_after:
            Retry-After ヘッダーがある場合に従うかどうか．
    """

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
            raise ValueError(
                "max_attempts には整数を指定してください"
            )

        if self.max_attempts < 1:
            raise ValueError(
                "max_attempts は1以上である必要があります"
            )

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
                    "retry_status_codes には有効な "
                    "HTTP ステータスコードを指定してください"
                )

            normalized_status_codes.add(status_code)

        object.__setattr__(
            self,
            "backoff_factor",
            normalized_backoff_factor,
        )
        object.__setattr__(
            self,
            "max_backoff",
            normalized_max_backoff,
        )
        object.__setattr__(
            self,
            "retry_status_codes",
            frozenset(normalized_status_codes),
        )

    def should_retry_status(self, status_code: int) -> bool:
        """
        指定された HTTP ステータスコードが再試行対象か判定する．
        """
        return status_code in self.retry_status_codes

    def get_backoff_seconds(
        self,
        *,
        failed_attempt: int,
        retry_after: float | None = None,
    ) -> float:
        """
        失敗した試行の後に待機する秒数を計算する．

        Args:
            failed_attempt:
                失敗した試行番号．初回は1．
            retry_after:
                Retry-After ヘッダーから取得した待機秒数．

        Returns:
            次回試行までの待機秒数．
        """
        exponential_backoff = self.backoff_factor * (
            2 ** max(0, failed_attempt - 1)
        )

        wait_seconds = min(
            exponential_backoff,
            self.max_backoff,
        )

        if self.respect_retry_after and retry_after is not None:
            wait_seconds = min(
                max(wait_seconds, retry_after),
                self.max_backoff,
            )

        return wait_seconds


class HTTPTransport:
    """
    Ondotori WebStorage API との HTTP 通信を担当する．

    外部から requests.Session を渡した場合，close() を呼んでも
    その Session は閉じない．Transport 内部で生成した Session
    だけを閉じる．
    """

    def __init__(
        self,
        *,
        timeout: Timeout = 10.0,
        retry_policy: RetryPolicy | None = None,
        session: requests.Session | None = None,
        logger_: logging.Logger | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """
        Args:
            timeout:
                HTTP タイムアウト秒．
                float または
                (接続タイムアウト, 読み込みタイムアウト)．
            retry_policy:
                リトライ方針．省略時は RetryPolicy() を使用する．
            session:
                外部から注入する requests.Session．
            logger_:
                使用するロガー．
            sleep:
                待機に使用する関数．テスト時に差し替え可能．
        """
        self.timeout = _validate_timeout(timeout)
        self.retry_policy = retry_policy or RetryPolicy()
        self._logger = logger_ or logger
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
        """
        JSON payload を POST し，JSON オブジェクトを返す．

        Args:
            url:
                API エンドポイント URL．
            payload:
                送信する JSON オブジェクト．
            headers:
                追加の HTTP ヘッダー．

        Returns:
            JSON オブジェクトを表す辞書．

        Raises:
            AuthenticationError:
                HTTP 401 または 403 が返された場合．
            RateLimitError:
                HTTP 429 が返され，再試行しても成功しなかった場合．
            APIError:
                その他の API エラー応答の場合．
            TransportError:
                接続失敗やタイムアウトが継続した場合．
            ResponseFormatError:
                成功応答が JSON オブジェクトではない場合．
        """
        if self._closed:
            raise RuntimeError(
                "HTTPTransport は既に閉じられています"
            )

        if not isinstance(url, str) or not url.strip():
            raise ValueError(
                "url には空でない文字列を指定してください"
            )

        if not isinstance(payload, Mapping):
            raise TypeError(
                "payload には Mapping を指定してください"
            )

        normalized_headers = dict(headers or {})
        last_transport_error: requests.RequestException | None = None
        last_response: requests.Response | None = None

        for attempt in range(
            1,
            self.retry_policy.max_attempts + 1,
        ):
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
            except (
                requests.Timeout,
                requests.ConnectionError,
            ) as exc:
                last_transport_error = exc

                if attempt >= self.retry_policy.max_attempts:
                    raise TransportError(
                        "Ondotori WebStorage API への通信に失敗しました"
                    ) from exc

                wait_seconds = self.retry_policy.get_backoff_seconds(
                    failed_attempt=attempt,
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
                # InvalidURL など，繰り返しても改善しない可能性が高い
                # requests 由来のその他の例外は再試行しない．
                raise TransportError(
                    "HTTP リクエストを実行できませんでした"
                ) from exc

            last_response = response

            if 200 <= response.status_code < 300:
                return self._decode_success_response(
                    response,
                    url=url,
                )

            if response.status_code in _AUTHENTICATION_STATUS_CODES:
                raise self._authentication_error(
                    response,
                    url=url,
                )

            if self.retry_policy.should_retry_status(
                response.status_code
            ):
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

            raise self._api_error_from_response(
                response,
                url=url,
            )

        # 通常は上の分岐ですべて return または raise する．
        if last_response is not None:
            raise self._api_error_from_response(
                last_response,
                url=url,
            )

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
        """
        成功レスポンスを JSON オブジェクトとして解釈する．
        """
        try:
            payload = response.json()
        except (requests.JSONDecodeError, ValueError) as exc:
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
        error_code, api_message, details = (
            _extract_error_information(response)
        )

        if api_message is None:
            api_message = (
                "Ondotori WebStorage API の認証に失敗しました"
            )

        return AuthenticationError(
            api_message,
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
        error_code, api_message, details = (
            _extract_error_information(response)
        )

        if response.status_code == 429:
            message = (
                api_message
                or "Ondotori WebStorage API のレート制限に達しました"
            )

            return RateLimitError(
                message,
                retry_after=retry_after,
                status_code=response.status_code,
                url=url,
                response_body=_response_body(response),
                error_code=error_code,
                details=details,
            )

        message = (
            api_message
            or (
                "Ondotori WebStorage API が"
                f"エラー応答を返しました: HTTP "
                f"{response.status_code}"
            )
        )

        return APIError(
            message,
            status_code=response.status_code,
            url=url,
            response_body=_response_body(response),
            error_code=error_code,
            details=details,
        )

    def close(self) -> None:
        """
        Transport 内部で生成した requests.Session を閉じる．

        外部から注入された Session は閉じない．
        """
        if self._closed:
            return

        if self._owns_session:
            self.session.close()

        self._closed = True

    def __enter__(self) -> HTTPTransport:
        if self._closed:
            raise RuntimeError(
                "閉じられた HTTPTransport は再利用できません"
            )

        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()


__all__ = [
    "JsonObject",
    "Timeout",
    "RetryPolicy",
    "HTTPTransport",
]