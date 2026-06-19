from __future__ import annotations

from typing import Any


class OndotoriError(Exception):
    """ondotori-client が送出する例外の基底クラス．"""


class ConfigurationError(OndotoriError, ValueError):
    """設定内容が不足している，または不正である場合の例外．"""


class RequestValidationError(OndotoriError, ValueError):
    """クライアントメソッドへ渡された引数が不正な場合の例外．"""


class TransportError(OndotoriError):
    """HTTP 通信そのものに失敗した場合の例外．"""


class APIError(OndotoriError):
    """Ondotori WebStorage API がエラー応答を返した場合の例外．"""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        url: str | None = None,
        response_body: str | None = None,
        error_code: str | int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.url = url
        self.response_body = response_body
        self.error_code = error_code
        self.details = details or {}

    def __str__(self) -> str:
        parts = [self.message]
        if self.status_code is not None:
            parts.append(f"status_code={self.status_code}")
        if self.error_code is not None:
            parts.append(f"error_code={self.error_code}")
        if self.url is not None:
            parts.append(f"url={self.url}")
        return " | ".join(parts)


class AuthenticationError(APIError):
    """API キー，ログイン ID，パスワード等の認証に失敗した場合の例外．"""


class RateLimitError(APIError):
    """API のレート制限に到達した場合の例外．"""

    def __init__(
        self,
        message: str,
        *,
        retry_after: float | None = None,
        status_code: int | None = 429,
        url: str | None = None,
        response_body: str | None = None,
        error_code: str | int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            status_code=status_code,
            url=url,
            response_body=response_body,
            error_code=error_code,
            details=details,
        )
        self.retry_after = retry_after


class ResponseFormatError(OndotoriError):
    """API 応答を期待する形式として解釈できない場合の例外．"""

    def __init__(
        self,
        message: str,
        *,
        url: str | None = None,
        response_body: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.url = url
        self.response_body = response_body

    def __str__(self) -> str:
        if self.url is None:
            return self.message
        return f"{self.message} | url={self.url}"


__all__ = [
    "APIError",
    "AuthenticationError",
    "ConfigurationError",
    "OndotoriError",
    "RateLimitError",
    "RequestValidationError",
    "ResponseFormatError",
    "TransportError",
]
