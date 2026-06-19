# 保存先:
# src/ondotori_client/exceptions.py
#
# ondotori-client 内で発生する例外を定義するモジュールです．
# 最初にこのファイルを追加し，後続の client.py，config.py，
# transport.py から共通して利用します．

from __future__ import annotations

from typing import Any


class OndotoriError(Exception):
    """ondotori-client が送出する例外の基底クラス．"""


class ConfigurationError(OndotoriError, ValueError):
    """
    設定内容が不足している，または不正である場合の例外．

    例:
        - 必須の認証情報が設定されていない
        - 未対応の device_type が指定された
        - RTR500 の親機が設定されていない
        - remote_map が存在しない親機を参照している
    """


class RequestValidationError(OndotoriError, ValueError):
    """
    クライアントメソッドへ渡された引数が不正な場合の例外．

    例:
        - hours と dt_from/dt_to が同時に指定された
        - hours または count が0以下
        - dt_from が dt_to より後
    """


class TransportError(OndotoriError):
    """
    HTTP通信そのものに失敗した場合の例外．

    例:
        - 接続失敗
        - DNS解決失敗
        - タイムアウト
        - TLSエラー
        - リトライ上限への到達
    """


class APIError(OndotoriError):
    """
    Ondotori WebStorage API がエラー応答を返した場合の例外．

    Attributes:
        status_code:
            HTTPステータスコード．不明な場合は None．
        url:
            リクエスト先URL．不明な場合は None．
        response_body:
            APIから返されたレスポンス本文．
        error_code:
            API固有のエラーコード．取得できない場合は None．
        details:
            その他の付加情報．
    """

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
    """
    APIキー，ログインID，パスワードなどの認証に失敗した場合の例外．

    主として HTTP 401 または 403 に対応します．
    """


class RateLimitError(APIError):
    """
    APIのレート制限に到達した場合の例外．

    主として HTTP 429 に対応します．

    Attributes:
        retry_after:
            APIが指定した再試行までの待機秒数．不明な場合は None．
    """

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
    """
    API応答を期待する形式として解釈できない場合の例外．

    例:
        - JSONとして解析できない
        - 必須フィールドが存在しない
        - unixtime を整数へ変換できない
        - data または devices の構造が想定と異なる
    """

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
    "OndotoriError",
    "ConfigurationError",
    "RequestValidationError",
    "TransportError",
    "APIError",
    "AuthenticationError",
    "RateLimitError",
    "ResponseFormatError",
]