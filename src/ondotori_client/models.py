# 保存先:
# src/ondotori_client/models.py
#
# クライアント内部で使用する解決済み機器情報，時間範囲，
# および解析済み測定データのモデルを定義するモジュールです．

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Any, Mapping

from .config import DeviceType, validate_device_type
from .exceptions import ConfigurationError, RequestValidationError


def _require_nonempty_string(
    value: object,
    *,
    field_name: str,
) -> str:
    """
    値が空でない文字列であることを確認する．
    """
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"{field_name!r} には空でない文字列を指定してください"
        )

    return value.strip()


def _optional_nonempty_string(
    value: object,
    *,
    field_name: str,
) -> str | None:
    """
    値が None または空でない文字列であることを確認する．
    """
    if value is None:
        return None

    if not isinstance(value, str):
        raise ValueError(
            f"{field_name!r} には文字列または None を指定してください"
        )

    normalized = value.strip()

    return normalized or None


def _require_aware_datetime(
    value: object,
    *,
    field_name: str,
) -> datetime:
    """
    値がタイムゾーン付き datetime であることを確認する．
    """
    if not isinstance(value, datetime):
        raise ValueError(
            f"{field_name!r} には datetime を指定してください"
        )

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(
            f"{field_name!r} にはタイムゾーン付き datetime を"
            "指定してください"
        )

    return value


def _normalize_metadata(
    value: Mapping[str, Any] | None,
    *,
    field_name: str,
) -> Mapping[str, Any]:
    """
    メタデータを外部から変更されない読み取り専用辞書へ変換する．
    """
    if value is None:
        return MappingProxyType({})

    if not isinstance(value, Mapping):
        raise ValueError(
            f"{field_name!r} には Mapping を指定してください"
        )

    return MappingProxyType(dict(value))


def _to_float_or_nan(value: object) -> float:
    """
    数値へ変換できない値を NaN として扱う．
    """
    if isinstance(value, bool):
        return math.nan

    try:
        return float(value)
    except (TypeError, ValueError):
        return math.nan


@dataclass(frozen=True, slots=True)
class ResolvedRemote:
    """
    設定を解決した後の機器情報．

    OndotoriClient は，利用者から受け取った remote_key を
    ClientConfig と照合し，このモデルへ変換してから API
    リクエストを構築する．

    Attributes:
        key:
            利用者がクライアントメソッドへ渡した機器名または
            シリアル番号．
        serial:
            API へ送信する子機または通常機器のシリアル番号．
        device_type:
            "default" または "rtr500"．
        base_serial:
            RTR500B 親機のシリアル番号．
            device_type が "rtr500" の場合は必須．
    """

    key: str
    serial: str
    device_type: DeviceType
    base_serial: str | None = None

    def __post_init__(self) -> None:
        normalized_key = _require_nonempty_string(
            self.key,
            field_name="key",
        )
        normalized_serial = _require_nonempty_string(
            self.serial,
            field_name="serial",
        )
        normalized_device_type = validate_device_type(
            self.device_type
        )
        normalized_base_serial = _optional_nonempty_string(
            self.base_serial,
            field_name="base_serial",
        )

        if (
            normalized_device_type == "rtr500"
            and normalized_base_serial is None
        ):
            raise ConfigurationError(
                f"RTR500 機器 {normalized_key!r} に"
                "親機シリアル番号が設定されていません"
            )

        if (
            normalized_device_type == "default"
            and normalized_base_serial is not None
        ):
            raise ConfigurationError(
                f"default 機器 {normalized_key!r} に"
                "base_serial は指定できません"
            )

        object.__setattr__(
            self,
            "key",
            normalized_key,
        )
        object.__setattr__(
            self,
            "serial",
            normalized_serial,
        )
        object.__setattr__(
            self,
            "device_type",
            normalized_device_type,
        )
        object.__setattr__(
            self,
            "base_serial",
            normalized_base_serial,
        )

    @property
    def is_rtr500(self) -> bool:
        """
        RTR500B 配下の機器であるかを返す．
        """
        return self.device_type == "rtr500"


@dataclass(frozen=True, slots=True)
class TimeRange:
    """
    API へ送信する Unix time の範囲．

    Attributes:
        start:
            開始 Unix time．指定しない場合は None．
        end:
            終了 Unix time．指定しない場合は None．
    """

    start: int | None = None
    end: int | None = None

    def __post_init__(self) -> None:
        if self.start is not None:
            if isinstance(self.start, bool) or not isinstance(
                self.start,
                int,
            ):
                raise RequestValidationError(
                    "start には整数の Unix time を指定してください"
                )

        if self.end is not None:
            if isinstance(self.end, bool) or not isinstance(
                self.end,
                int,
            ):
                raise RequestValidationError(
                    "end には整数の Unix time を指定してください"
                )

        if (
            self.start is not None
            and self.end is not None
            and self.start > self.end
        ):
            raise RequestValidationError(
                "開始日時は終了日時以前である必要があります"
            )

    def to_payload(self) -> dict[str, int]:
        """
        WebStorage API のリクエスト形式へ変換する．
        """
        payload: dict[str, int] = {}

        if self.start is not None:
            payload["unixtime-from"] = self.start

        if self.end is not None:
            payload["unixtime-to"] = self.end

        return payload

    @property
    def is_empty(self) -> bool:
        """
        開始・終了時刻がどちらも未指定であるかを返す．
        """
        return self.start is None and self.end is None


@dataclass(frozen=True, slots=True)
class ChannelReading:
    """
    1つの測定チャンネルの値．

    機種依存のチャンネル構成を保持できる汎用モデルであり，
    温度・湿度以外の測定値にも使用できる．

    Attributes:
        key:
            チャンネルを識別するキー．例: "ch1"，"ch2"．
        value:
            解析済みの値．数値，文字列，または None．
        unit:
            単位．例: "°C"，"%"．
        name:
            チャンネルの表示名．
        metadata:
            API 応答に含まれるその他の情報．
    """

    key: str
    value: float | str | None
    unit: str | None = None
    name: str | None = None
    metadata: Mapping[str, Any] = field(
        default_factory=dict,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        normalized_key = _require_nonempty_string(
            self.key,
            field_name="channel.key",
        )
        normalized_unit = _optional_nonempty_string(
            self.unit,
            field_name="channel.unit",
        )
        normalized_name = _optional_nonempty_string(
            self.name,
            field_name="channel.name",
        )
        normalized_metadata = _normalize_metadata(
            self.metadata,
            field_name="channel.metadata",
        )

        if isinstance(self.value, bool):
            raise ValueError(
                "channel.value に bool は指定できません"
            )

        if self.value is not None and not isinstance(
            self.value,
            (int, float, str),
        ):
            raise ValueError(
                "channel.value には数値，文字列，または None を"
                "指定してください"
            )

        normalized_value: float | str | None

        if isinstance(self.value, int):
            normalized_value = float(self.value)
        else:
            normalized_value = self.value

        object.__setattr__(
            self,
            "key",
            normalized_key,
        )
        object.__setattr__(
            self,
            "value",
            normalized_value,
        )
        object.__setattr__(
            self,
            "unit",
            normalized_unit,
        )
        object.__setattr__(
            self,
            "name",
            normalized_name,
        )
        object.__setattr__(
            self,
            "metadata",
            normalized_metadata,
        )

    @property
    def numeric_value(self) -> float:
        """
        値を float として返す．

        数値へ変換できない場合は NaN を返す．
        """
        return _to_float_or_nan(self.value)

    def to_dict(self) -> dict[str, Any]:
        """
        通常の辞書へ変換する．
        """
        result: dict[str, Any] = {
            "key": self.key,
            "value": self.value,
        }

        if self.unit is not None:
            result["unit"] = self.unit

        if self.name is not None:
            result["name"] = self.name

        if self.metadata:
            result["metadata"] = dict(self.metadata)

        return result


@dataclass(frozen=True, slots=True)
class MeasurementRecord:
    """
    1時点における複数チャンネルの測定記録．

    Attributes:
        timestamp:
            タイムゾーン付きの測定日時．
        channels:
            測定チャンネルのタプル．
        remote_serial:
            測定機器のシリアル番号．
        metadata:
            API 応答に含まれるその他の情報．
    """

    timestamp: datetime
    channels: tuple[ChannelReading, ...]
    remote_serial: str | None = None
    metadata: Mapping[str, Any] = field(
        default_factory=dict,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        normalized_timestamp = _require_aware_datetime(
            self.timestamp,
            field_name="timestamp",
        )

        try:
            normalized_channels = tuple(self.channels)
        except TypeError as exc:
            raise ValueError(
                "channels には ChannelReading の反復可能オブジェクトを"
                "指定してください"
            ) from exc

        channel_keys: set[str] = set()

        for channel in normalized_channels:
            if not isinstance(channel, ChannelReading):
                raise ValueError(
                    "channels の各要素は ChannelReading である"
                    "必要があります"
                )

            if channel.key in channel_keys:
                raise ValueError(
                    f"チャンネルキーが重複しています: "
                    f"{channel.key!r}"
                )

            channel_keys.add(channel.key)

        normalized_remote_serial = _optional_nonempty_string(
            self.remote_serial,
            field_name="remote_serial",
        )
        normalized_metadata = _normalize_metadata(
            self.metadata,
            field_name="measurement.metadata",
        )

        object.__setattr__(
            self,
            "timestamp",
            normalized_timestamp,
        )
        object.__setattr__(
            self,
            "channels",
            normalized_channels,
        )
        object.__setattr__(
            self,
            "remote_serial",
            normalized_remote_serial,
        )
        object.__setattr__(
            self,
            "metadata",
            normalized_metadata,
        )

    def get_channel(
        self,
        key: str,
    ) -> ChannelReading | None:
        """
        指定したキーのチャンネルを返す．

        見つからない場合は None を返す．
        """
        normalized_key = _require_nonempty_string(
            key,
            field_name="key",
        )

        for channel in self.channels:
            if channel.key == normalized_key:
                return channel

        return None

    def require_channel(
        self,
        key: str,
    ) -> ChannelReading:
        """
        指定したキーのチャンネルを返す．

        見つからない場合は KeyError を送出する．
        """
        channel = self.get_channel(key)

        if channel is None:
            raise KeyError(
                f"測定記録にチャンネル {key!r} がありません"
            )

        return channel

    def to_flat_dict(self) -> dict[str, Any]:
        """
        DataFrame などへ渡しやすい1階層の辞書へ変換する．
        """
        result: dict[str, Any] = {
            "timestamp": self.timestamp,
        }

        if self.remote_serial is not None:
            result["remote_serial"] = self.remote_serial

        for channel in self.channels:
            result[channel.key] = channel.value

        return result

    def to_dict(self) -> dict[str, Any]:
        """
        JSON 化しやすい辞書へ変換する．
        """
        result: dict[str, Any] = {
            "timestamp": self.timestamp.isoformat(),
            "channels": [
                channel.to_dict()
                for channel in self.channels
            ],
        }

        if self.remote_serial is not None:
            result["remote_serial"] = self.remote_serial

        if self.metadata:
            result["metadata"] = dict(self.metadata)

        return result


@dataclass(frozen=True, slots=True)
class TemperatureHumidityReading:
    """
    温湿度機器向けの簡易測定モデル．

    既存の parse_current() および parse_data() と互換性のある
    温度・湿度専用の値を保持する．

    Attributes:
        timestamp:
            タイムゾーン付きの測定日時．
        temperature_c:
            温度．単位は °C．取得できない場合は NaN．
        humidity_percent:
            相対湿度．単位は %．取得できない場合は NaN．
        remote_serial:
            測定機器のシリアル番号．
    """

    timestamp: datetime
    temperature_c: float
    humidity_percent: float
    remote_serial: str | None = None

    def __post_init__(self) -> None:
        normalized_timestamp = _require_aware_datetime(
            self.timestamp,
            field_name="timestamp",
        )
        normalized_temperature = _to_float_or_nan(
            self.temperature_c
        )
        normalized_humidity = _to_float_or_nan(
            self.humidity_percent
        )
        normalized_remote_serial = _optional_nonempty_string(
            self.remote_serial,
            field_name="remote_serial",
        )

        object.__setattr__(
            self,
            "timestamp",
            normalized_timestamp,
        )
        object.__setattr__(
            self,
            "temperature_c",
            normalized_temperature,
        )
        object.__setattr__(
            self,
            "humidity_percent",
            normalized_humidity,
        )
        object.__setattr__(
            self,
            "remote_serial",
            normalized_remote_serial,
        )

    def as_tuple(
        self,
    ) -> tuple[datetime, float, float]:
        """
        既存 API と同じ
        (timestamp, temperature_c, humidity_percent)
        のタプルを返す．
        """
        return (
            self.timestamp,
            self.temperature_c,
            self.humidity_percent,
        )

    def to_dict(self) -> dict[str, Any]:
        """
        DataFrame などへ渡しやすい辞書へ変換する．
        """
        result: dict[str, Any] = {
            "timestamp": self.timestamp,
            "temp_C": self.temperature_c,
            "hum_%": self.humidity_percent,
        }

        if self.remote_serial is not None:
            result["remote_serial"] = self.remote_serial

        return result


__all__ = [
    "ResolvedRemote",
    "TimeRange",
    "ChannelReading",
    "MeasurementRecord",
    "TemperatureHumidityReading",
]