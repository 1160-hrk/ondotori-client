from __future__ import annotations

import logging
import os
import warnings
from collections.abc import Mapping
from datetime import UTC, datetime, tzinfo
from types import TracebackType
from typing import TYPE_CHECKING, Any, Literal, overload

import requests

from .config import ClientConfig, DeviceType, validate_device_type
from .exceptions import ConfigurationError, RequestValidationError
from .models import MeasurementRecord, ResolvedRemote, TimeRange
from .parsers import parse_data_records, parse_temperature_humidity_data
from .transport import HTTPTransport, RetryPolicy, Timeout

if TYPE_CHECKING:
    import pandas as pd


DateTimeInput = datetime | int | float | str
_LOGGER = logging.getLogger(__name__)


class OndotoriClient:
    """Ondotori WebStorage API クライアント．"""

    _URL_CURRENT = "https://api.webstorage.jp/v1/devices/current"
    _URL_DATA_DEFAULT = "https://api.webstorage.jp/v1/devices/data"
    _URL_DATA_RTR500 = "https://api.webstorage.jp/v1/devices/data-rtr500"
    _URL_LATEST_DEFAULT = "https://api.webstorage.jp/v1/devices/latest-data"
    _URL_LATEST_RTR500 = (
        "https://api.webstorage.jp/v1/devices/latest-data-rtr500"
    )
    _URL_ALERT = "https://api.webstorage.jp/v1/devices/alert"

    _HEADERS = {
        "Content-Type": "application/json",
        "X-HTTP-Method-Override": "GET",
    }

    def __init__(
        self,
        config: (
            ClientConfig
            | str
            | os.PathLike[str]
            | Mapping[str, Any]
            | None
        ) = None,
        api_key: str | None = None,
        login_id: str | None = None,
        login_pass: str | None = None,
        base_serial: str | None = None,
        device_type: DeviceType = "default",
        retries: int = 3,
        timeout: Timeout = 10.0,
        verbose: bool = False,
        session: requests.Session | None = None,
        logger: logging.Logger | None = None,
        transport: HTTPTransport | None = None,
        default_timezone: tzinfo = UTC,
        auto_save_config: bool | None = None,
        config_path: str | os.PathLike[str] | None = None,
    ) -> None:
        """
        config には ClientConfig，設定ファイルパス，または設定辞書を
        指定する．config を省略する場合は認証情報を直接指定する．

        auto_save_config と config_path は旧 API 互換用であり，設定の
        自動保存は行わない．
        """
        self.logger = logger or _LOGGER
        if verbose:
            self.logger.setLevel(logging.DEBUG)

        self.default_timezone = self._validate_timezone(default_timezone)
        self.default_device_type = validate_device_type(device_type)
        self.config = self._build_config(
            config=config,
            api_key=api_key,
            login_id=login_id,
            login_pass=login_pass,
            base_serial=base_serial,
        )

        if auto_save_config:
            warnings.warn(
                "auto_save_config は廃止されました．設定は自動保存されません．",
                FutureWarning,
                stacklevel=2,
            )
        if config_path is not None:
            warnings.warn(
                "config_path は自動保存の廃止に伴い使用されません．",
                FutureWarning,
                stacklevel=2,
            )

        if transport is not None and session is not None:
            raise ValueError("transport と session は同時に指定できません")

        if transport is None:
            self._transport = HTTPTransport(
                timeout=timeout,
                retry_policy=RetryPolicy(max_attempts=retries),
                session=session,
                logger_=self.logger,
            )
            self._owns_transport = True
        else:
            self._transport = transport
            self._owns_transport = False

        self._closed = False

    @classmethod
    def from_file(
        cls,
        path: str | os.PathLike[str],
        **kwargs: Any,
    ) -> OndotoriClient:
        return cls(config=ClientConfig.from_file(path), **kwargs)

    @classmethod
    def from_mapping(
        cls,
        data: Mapping[str, Any],
        **kwargs: Any,
    ) -> OndotoriClient:
        return cls(config=ClientConfig.from_mapping(data), **kwargs)

    @classmethod
    def from_credentials(
        cls,
        *,
        api_key: str,
        login_id: str,
        login_pass: str,
        base_serial: str | None = None,
        **kwargs: Any,
    ) -> OndotoriClient:
        return cls(
            config=ClientConfig.from_credentials(
                api_key=api_key,
                login_id=login_id,
                login_pass=login_pass,
                base_serial=base_serial,
            ),
            **kwargs,
        )

    @staticmethod
    def _validate_timezone(value: tzinfo) -> tzinfo:
        if not isinstance(value, tzinfo):
            raise TypeError("default_timezone には tzinfo を指定してください")
        try:
            offset = datetime.now(value).utcoffset()
        except Exception as exc:
            raise ValueError("default_timezone が不正です") from exc
        if offset is None:
            raise ValueError("default_timezone が不正です")
        return value

    @staticmethod
    def _build_config(
        *,
        config: (
            ClientConfig
            | str
            | os.PathLike[str]
            | Mapping[str, Any]
            | None
        ),
        api_key: str | None,
        login_id: str | None,
        login_pass: str | None,
        base_serial: str | None,
    ) -> ClientConfig:
        direct_values = (api_key, login_id, login_pass, base_serial)

        if config is not None and any(v is not None for v in direct_values):
            raise ConfigurationError(
                "config と直接認証情報は同時に指定できません"
            )
        if isinstance(config, ClientConfig):
            return config
        if isinstance(config, (str, os.PathLike)):
            return ClientConfig.from_file(config)
        if isinstance(config, Mapping):
            return ClientConfig.from_mapping(config)
        if config is not None:
            raise TypeError(
                "config には ClientConfig，パス，Mapping，または None を"
                "指定してください"
            )

        missing = [
            name
            for name, value in (
                ("api_key", api_key),
                ("login_id", login_id),
                ("login_pass", login_pass),
            )
            if value is None
        ]
        if missing:
            raise ConfigurationError(
                "認証情報が不足しています: " + ", ".join(missing)
            )

        return ClientConfig.from_credentials(
            api_key=api_key,
            login_id=login_id,
            login_pass=login_pass,
            base_serial=base_serial,
        )

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("OndotoriClient は既に閉じられています")

    def _auth_payload(self) -> dict[str, str]:
        return self.config.credentials.to_api_payload()

    def _resolve_remote_identity(
        self,
        remote_key: str,
        device_type: DeviceType | None = None,
    ) -> tuple[str, DeviceType, str | None]:
        if not isinstance(remote_key, str) or not remote_key.strip():
            raise RequestValidationError(
                "remote_key には空でない文字列を指定してください"
            )

        key = remote_key.strip()
        configured = self.config.remotes.get(key)

        if configured is None:
            serial = key
            resolved_type = (
                validate_device_type(device_type)
                if device_type is not None
                else self.default_device_type
            )
            base_name = self.config.default_rtr500_base
        else:
            serial = configured.serial
            resolved_type = (
                validate_device_type(device_type)
                if device_type is not None
                else configured.device_type
            )
            base_name = configured.base or self.config.default_rtr500_base

        return serial, resolved_type, base_name

    def _resolve_remote(
        self,
        remote_key: str,
        device_type: DeviceType | None = None,
    ) -> ResolvedRemote:
        serial, resolved_type, base_name = self._resolve_remote_identity(
            remote_key,
            device_type,
        )

        if resolved_type == "default":
            return ResolvedRemote(
                key=remote_key,
                serial=serial,
                device_type="default",
            )

        if base_name is None:
            raise ConfigurationError(
                f"RTR500 機器 {remote_key!r} に親機が設定されていません"
            )
        try:
            base_serial = self.config.bases[base_name].serial
        except KeyError as exc:
            raise ConfigurationError(
                f"親機 {base_name!r} が bases に定義されていません"
            ) from exc

        return ResolvedRemote(
            key=remote_key,
            serial=serial,
            device_type="rtr500",
            base_serial=base_serial,
        )

    def _to_timestamp(
        self,
        value: DateTimeInput,
        *,
        field_name: str,
    ) -> int:
        if isinstance(value, bool):
            raise RequestValidationError(
                f"{field_name} に bool は指定できません"
            )
        if isinstance(value, (int, float)):
            try:
                return int(value)
            except (OverflowError, ValueError) as exc:
                raise RequestValidationError(
                    f"{field_name} を Unix time に変換できません"
                ) from exc

        if isinstance(value, datetime):
            parsed = value
        elif isinstance(value, str):
            normalized = value.strip()
            if not normalized:
                raise RequestValidationError(
                    f"{field_name} に空文字列は指定できません"
                )
            try:
                return int(float(normalized))
            except ValueError:
                pass
            if normalized.endswith("Z"):
                normalized = normalized[:-1] + "+00:00"
            try:
                parsed = datetime.fromisoformat(normalized)
            except ValueError as exc:
                raise RequestValidationError(
                    f"{field_name} を日時として解釈できません: {value!r}"
                ) from exc
        else:
            raise RequestValidationError(
                f"{field_name} には datetime，Unix time，または "
                "ISO 8601 文字列を指定してください"
            )

        if parsed.tzinfo is None or parsed.utcoffset() is None:
            parsed = parsed.replace(tzinfo=self.default_timezone)

        try:
            return int(parsed.timestamp())
        except (OverflowError, OSError, ValueError) as exc:
            raise RequestValidationError(
                f"{field_name} を Unix time に変換できません"
            ) from exc

    def _build_time_range(
        self,
        *,
        dt_from: DateTimeInput | None,
        dt_to: DateTimeInput | None,
        hours: float | None,
    ) -> TimeRange:
        if hours is not None and (dt_from is not None or dt_to is not None):
            raise RequestValidationError(
                "hours と dt_from/dt_to は同時に指定できません"
            )

        if hours is not None:
            if isinstance(hours, bool):
                raise RequestValidationError(
                    "hours には正の数値を指定してください"
                )
            try:
                normalized_hours = float(hours)
            except (TypeError, ValueError) as exc:
                raise RequestValidationError(
                    "hours には正の数値を指定してください"
                ) from exc
            if normalized_hours <= 0:
                raise RequestValidationError(
                    "hours は正の値である必要があります"
                )

            end = int(datetime.now(UTC).timestamp())
            return TimeRange(
                start=int(end - normalized_hours * 3600),
                end=end,
            )

        start = (
            self._to_timestamp(dt_from, field_name="dt_from")
            if dt_from is not None
            else None
        )
        end = (
            self._to_timestamp(dt_to, field_name="dt_to")
            if dt_to is not None
            else None
        )
        return TimeRange(start=start, end=end)

    @staticmethod
    def _validate_count(count: int | None) -> int | None:
        if count is None:
            return None
        if isinstance(count, bool) or not isinstance(count, int):
            raise RequestValidationError(
                "count には正の整数を指定してください"
            )
        if count <= 0:
            raise RequestValidationError(
                "count は正の値である必要があります"
            )
        return count

    def _post(
        self,
        url: str,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        self._ensure_open()
        return self._transport.post_json(
            url,
            payload,
            headers=self._HEADERS,
        )

    def get_current(
        self,
        remote_key: str,
        *,
        device_type: DeviceType | None = None,
    ) -> dict[str, Any]:
        serial, _, _ = self._resolve_remote_identity(
            remote_key,
            device_type,
        )
        return self._post(
            self._URL_CURRENT,
            {
                **self._auth_payload(),
                "remote-serial": [serial],
            },
        )

    @overload
    def get_data(
        self,
        remote_key: str,
        dt_from: DateTimeInput | None = None,
        dt_to: DateTimeInput | None = None,
        count: int | None = None,
        hours: float | None = None,
        as_df: Literal[False] = False,
        device_type: DeviceType | None = None,
    ) -> dict[str, Any]: ...

    @overload
    def get_data(
        self,
        remote_key: str,
        dt_from: DateTimeInput | None = None,
        dt_to: DateTimeInput | None = None,
        count: int | None = None,
        hours: float | None = None,
        as_df: Literal[True] = True,
        device_type: DeviceType | None = None,
    ) -> pd.DataFrame: ...

    def get_data(
        self,
        remote_key: str,
        dt_from: DateTimeInput | None = None,
        dt_to: DateTimeInput | None = None,
        count: int | None = None,
        hours: float | None = None,
        as_df: bool = False,
        device_type: DeviceType | None = None,
    ) -> dict[str, Any] | pd.DataFrame:
        remote = self._resolve_remote(remote_key, device_type)
        time_range = self._build_time_range(
            dt_from=dt_from,
            dt_to=dt_to,
            hours=hours,
        )
        count = self._validate_count(count)

        payload: dict[str, Any] = {
            **self._auth_payload(),
            "remote-serial": remote.serial,
            **time_range.to_payload(),
        }

        if remote.is_rtr500:
            if count is not None:
                raise RequestValidationError(
                    "count は rtr500 データ取得では使用できません"
                )
            url = self._URL_DATA_RTR500
            payload["base-serial"] = remote.base_serial
        else:
            url = self._URL_DATA_DEFAULT
            if count is not None:
                payload["number"] = count

        result = self._post(url, payload)
        if as_df:
            return self._to_temperature_humidity_dataframe(result)
        return result

    def get_data_raw(
        self,
        remote_key: str,
        dt_from: DateTimeInput | None = None,
        dt_to: DateTimeInput | None = None,
        count: int | None = None,
        hours: float | None = None,
        device_type: DeviceType | None = None,
    ) -> dict[str, Any]:
        return self.get_data(
            remote_key,
            dt_from=dt_from,
            dt_to=dt_to,
            count=count,
            hours=hours,
            as_df=False,
            device_type=device_type,
        )

    def get_data_records(
        self,
        remote_key: str,
        dt_from: DateTimeInput | None = None,
        dt_to: DateTimeInput | None = None,
        count: int | None = None,
        hours: float | None = None,
        device_type: DeviceType | None = None,
    ) -> list[MeasurementRecord]:
        raw = self.get_data_raw(
            remote_key,
            dt_from=dt_from,
            dt_to=dt_to,
            count=count,
            hours=hours,
            device_type=device_type,
        )
        return parse_data_records(raw, tz=self.default_timezone)

    def get_data_frame(
        self,
        remote_key: str,
        dt_from: DateTimeInput | None = None,
        dt_to: DateTimeInput | None = None,
        count: int | None = None,
        hours: float | None = None,
        device_type: DeviceType | None = None,
    ) -> pd.DataFrame:
        raw = self.get_data_raw(
            remote_key,
            dt_from=dt_from,
            dt_to=dt_to,
            count=count,
            hours=hours,
            device_type=device_type,
        )
        return self._to_temperature_humidity_dataframe(raw)

    def _to_temperature_humidity_dataframe(
        self,
        raw: Mapping[str, Any],
    ) -> pd.DataFrame:
        try:
            import pandas as pd
        except ImportError as exc:
            raise ImportError(
                "pandas が必要です．"
                "`pip install ondotori-client[dataframe]` を実行してください"
            ) from exc

        readings = parse_temperature_humidity_data(
            raw,
            tz=self.default_timezone,
        )
        return pd.DataFrame(
            {
                "timestamp": [r.timestamp for r in readings],
                "temp_C": [r.temperature_c for r in readings],
                "hum_%": [r.humidity_percent for r in readings],
            }
        )

    def get_latest_data(
        self,
        remote_key: str,
        device_type: DeviceType | None = None,
    ) -> dict[str, Any]:
        remote = self._resolve_remote(remote_key, device_type)
        payload: dict[str, Any] = {
            **self._auth_payload(),
            "remote-serial": remote.serial,
        }

        if remote.is_rtr500:
            url = self._URL_LATEST_RTR500
            payload["base-serial"] = remote.base_serial
        else:
            url = self._URL_LATEST_DEFAULT

        return self._post(url, payload)

    def get_latest_records(
        self,
        remote_key: str,
        device_type: DeviceType | None = None,
    ) -> list[MeasurementRecord]:
        raw = self.get_latest_data(
            remote_key,
            device_type=device_type,
        )
        return parse_data_records(raw, tz=self.default_timezone)

    def get_alerts(self, remote_key: str) -> dict[str, Any]:
        remote = self._resolve_remote(
            remote_key,
            device_type="rtr500",
        )
        return self._post(
            self._URL_ALERT,
            {
                **self._auth_payload(),
                "remote-serial": remote.serial,
                "base-serial": remote.base_serial,
            },
        )

    def close(self) -> None:
        if self._closed:
            return
        if self._owns_transport:
            self._transport.close()
        self._closed = True

    def __enter__(self) -> OndotoriClient:
        self._ensure_open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()


__all__ = ["DateTimeInput", "OndotoriClient"]
