from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Any

from .config import DeviceType, validate_device_type
from .exceptions import ConfigurationError, RequestValidationError


def _require_nonempty_string(value: object, *, field_name: str) -> str:
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
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(
            f"{field_name!r} には文字列または None を指定してください"
        )
    normalized = value.strip()
    return normalized or None


def _require_aware_datetime(value: object, *, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError(f"{field_name!r} には datetime を指定してください")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(
            f"{field_name!r} にはタイムゾーン付き datetime を指定してください"
        )
    return value


def _normalize_metadata(
    value: Mapping[str, Any] | None,
    *,
    field_name: str,
) -> Mapping[str, Any]:
    if value is None:
        return MappingProxyType({})
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name!r} には Mapping を指定してください")
    return MappingProxyType(dict(value))


def _to_float_or_nan(value: object) -> float:
    if isinstance(value, bool):
        return math.nan
    if not isinstance(value, (int, float, str)):
        return math.nan
    try:
        return float(value)
    except ValueError:
        return math.nan


@dataclass(frozen=True, slots=True)
class ResolvedRemote:
    """設定を解決した後の機器情報．"""

    key: str
    serial: str
    device_type: DeviceType
    base_serial: str | None = None

    def __post_init__(self) -> None:
        normalized_key = _require_nonempty_string(self.key, field_name="key")
        normalized_serial = _require_nonempty_string(
            self.serial,
            field_name="serial",
        )
        normalized_device_type = validate_device_type(self.device_type)
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
                f"default 機器 {normalized_key!r} に base_serial は指定できません"
            )

        object.__setattr__(self, "key", normalized_key)
        object.__setattr__(self, "serial", normalized_serial)
        object.__setattr__(self, "device_type", normalized_device_type)
        object.__setattr__(self, "base_serial", normalized_base_serial)

    @property
    def is_rtr500(self) -> bool:
        return self.device_type == "rtr500"


@dataclass(frozen=True, slots=True)
class TimeRange:
    """API へ送信する Unix time の範囲．"""

    start: int | None = None
    end: int | None = None

    def __post_init__(self) -> None:
        if self.start is not None and (
            isinstance(self.start, bool) or not isinstance(self.start, int)
        ):
            raise RequestValidationError(
                "start には整数の Unix time を指定してください"
            )
        if self.end is not None and (
            isinstance(self.end, bool) or not isinstance(self.end, int)
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
        payload: dict[str, int] = {}
        if self.start is not None:
            payload["unixtime-from"] = self.start
        if self.end is not None:
            payload["unixtime-to"] = self.end
        return payload

    @property
    def is_empty(self) -> bool:
        return self.start is None and self.end is None


@dataclass(frozen=True, slots=True)
class ChannelReading:
    """1つの測定チャンネルの値．"""

    key: str
    value: float | int | str | None
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
            raise ValueError("channel.value に bool は指定できません")
        if self.value is not None and not isinstance(
            self.value,
            (int, float, str),
        ):
            raise ValueError(
                "channel.value には数値，文字列，または None を指定してください"
            )

        normalized_value: float | str | None
        if isinstance(self.value, int):
            normalized_value = float(self.value)
        else:
            normalized_value = self.value

        object.__setattr__(self, "key", normalized_key)
        object.__setattr__(self, "value", normalized_value)
        object.__setattr__(self, "unit", normalized_unit)
        object.__setattr__(self, "name", normalized_name)
        object.__setattr__(self, "metadata", normalized_metadata)

    @property
    def numeric_value(self) -> float:
        return _to_float_or_nan(self.value)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"key": self.key, "value": self.value}
        if self.unit is not None:
            result["unit"] = self.unit
        if self.name is not None:
            result["name"] = self.name
        if self.metadata:
            result["metadata"] = dict(self.metadata)
        return result


@dataclass(frozen=True, slots=True)
class MeasurementRecord:
    """1時点における複数チャンネルの測定記録．"""

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
                    "channels の各要素は ChannelReading である必要があります"
                )
            if channel.key in channel_keys:
                raise ValueError(
                    f"チャンネルキーが重複しています: {channel.key!r}"
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

        object.__setattr__(self, "timestamp", normalized_timestamp)
        object.__setattr__(self, "channels", normalized_channels)
        object.__setattr__(self, "remote_serial", normalized_remote_serial)
        object.__setattr__(self, "metadata", normalized_metadata)

    def get_channel(self, key: str) -> ChannelReading | None:
        normalized_key = _require_nonempty_string(key, field_name="key")
        for channel in self.channels:
            if channel.key == normalized_key:
                return channel
        return None

    def require_channel(self, key: str) -> ChannelReading:
        channel = self.get_channel(key)
        if channel is None:
            raise KeyError(f"測定記録にチャンネル {key!r} がありません")
        return channel

    def to_flat_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"timestamp": self.timestamp}
        if self.remote_serial is not None:
            result["remote_serial"] = self.remote_serial
        for channel in self.channels:
            result[channel.key] = channel.value
        return result

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "timestamp": self.timestamp.isoformat(),
            "channels": [channel.to_dict() for channel in self.channels],
        }
        if self.remote_serial is not None:
            result["remote_serial"] = self.remote_serial
        if self.metadata:
            result["metadata"] = dict(self.metadata)
        return result


@dataclass(frozen=True, slots=True)
class TemperatureHumidityReading:
    """温湿度機器向けの簡易測定モデル．"""

    timestamp: datetime
    temperature_c: float
    humidity_percent: float
    remote_serial: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "timestamp",
            _require_aware_datetime(self.timestamp, field_name="timestamp"),
        )
        object.__setattr__(
            self,
            "temperature_c",
            _to_float_or_nan(self.temperature_c),
        )
        object.__setattr__(
            self,
            "humidity_percent",
            _to_float_or_nan(self.humidity_percent),
        )
        object.__setattr__(
            self,
            "remote_serial",
            _optional_nonempty_string(
                self.remote_serial,
                field_name="remote_serial",
            ),
        )

    def as_tuple(self) -> tuple[datetime, float, float]:
        return (
            self.timestamp,
            self.temperature_c,
            self.humidity_percent,
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "timestamp": self.timestamp,
            "temp_C": self.temperature_c,
            "hum_%": self.humidity_percent,
        }
        if self.remote_serial is not None:
            result["remote_serial"] = self.remote_serial
        return result


__all__ = [
    "ChannelReading",
    "MeasurementRecord",
    "ResolvedRemote",
    "TemperatureHumidityReading",
    "TimeRange",
]
