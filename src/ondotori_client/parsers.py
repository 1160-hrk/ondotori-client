# 保存先:
# src/ondotori_client/parsers.py
#
# Ondotori WebStorage API の JSON 応答を，MeasurementRecord や
# TemperatureHumidityReading へ変換するモジュールです．
#
# 既存 API との互換性のため，以下の関数も維持します．
#
# - parse_current()
# - parse_data()
#
# Unix time はデフォルトで UTC のタイムゾーン付き datetime に
# 変換します．日本時間で取得する場合は，次のように指定できます．
#
#     from zoneinfo import ZoneInfo
#
#     parse_current(response, tz=ZoneInfo("Asia/Tokyo"))

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, tzinfo
from typing import Any, Final

from .exceptions import ResponseFormatError
from .models import (
    ChannelReading,
    MeasurementRecord,
    TemperatureHumidityReading,
)


_CHANNEL_KEY_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^ch(?P<number>\d+)$",
    flags=re.IGNORECASE,
)

_REMOTE_SERIAL_KEYS: Final[tuple[str, ...]] = (
    "remote-serial",
    "remote_serial",
    "remoteSerial",
    "serial",
)

_CHANNEL_METADATA_SUFFIXES: Final[tuple[str, ...]] = (
    "_unit",
    "-unit",
    "_name",
    "-name",
)

_CURRENT_CHANNEL_KEYS: Final[frozenset[str]] = frozenset(
    {
        "channel",
        "channels",
    }
)

_TIMESTAMP_KEYS: Final[tuple[str, ...]] = (
    "unixtime",
    "unix_time",
    "timestamp",
)


def _require_mapping(
    value: object,
    *,
    field_name: str,
) -> Mapping[str, Any]:
    """
    値が文字列キーの Mapping であることを確認する．
    """
    if not isinstance(value, Mapping):
        raise ResponseFormatError(
            f"{field_name} が JSON オブジェクトではありません"
        )

    for key in value:
        if not isinstance(key, str):
            raise ResponseFormatError(
                f"{field_name} に文字列以外のキーが含まれています"
            )

    return value


def _require_sequence(
    value: object,
    *,
    field_name: str,
) -> Sequence[Any]:
    """
    値が配列であることを確認する．

    文字列や bytes は配列として扱わない．
    """
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes, bytearray))
    ):
        raise ResponseFormatError(
            f"{field_name} が JSON 配列ではありません"
        )

    return value


def _validate_timezone(tz: tzinfo) -> tzinfo:
    """
    datetime へ使用できるタイムゾーンであることを確認する．
    """
    if not isinstance(tz, tzinfo):
        raise TypeError(
            "tz には datetime.tzinfo を指定してください"
        )

    try:
        offset = datetime.now(tz).utcoffset()
    except Exception as exc:
        raise ValueError(
            "tz をタイムゾーンとして使用できません"
        ) from exc

    if offset is None:
        raise ValueError(
            "tz には有効なタイムゾーンを指定してください"
        )

    return tz


def _extract_timestamp_value(
    data: Mapping[str, Any],
    *,
    field_name: str,
) -> object:
    """
    Mapping から時刻値を取得する．
    """
    for key in _TIMESTAMP_KEYS:
        if key in data:
            return data[key]

    expected_keys = ", ".join(repr(key) for key in _TIMESTAMP_KEYS)

    raise ResponseFormatError(
        f"{field_name} に時刻情報がありません．"
        f"期待するキー: {expected_keys}"
    )


def _parse_timestamp(
    value: object,
    *,
    tz: tzinfo,
    field_name: str,
) -> datetime:
    """
    Unix time または ISO 8601 文字列を datetime へ変換する．

    数値または数値文字列は Unix time として解釈する．
    それ以外の文字列は ISO 8601 として解釈する．
    """
    validated_timezone = _validate_timezone(tz)

    if isinstance(value, bool) or value is None:
        raise ResponseFormatError(
            f"{field_name} が有効な時刻ではありません: {value!r}"
        )

    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(
                float(value),
                tz=validated_timezone,
            )
        except (
            OSError,
            OverflowError,
            ValueError,
        ) as exc:
            raise ResponseFormatError(
                f"{field_name} を日時へ変換できません: {value!r}"
            ) from exc

    if not isinstance(value, str):
        raise ResponseFormatError(
            f"{field_name} が数値または文字列ではありません"
        )

    normalized = value.strip()

    if not normalized:
        raise ResponseFormatError(
            f"{field_name} が空文字列です"
        )

    try:
        unix_time = float(normalized)
    except ValueError:
        unix_time = None

    if unix_time is not None:
        try:
            return datetime.fromtimestamp(
                unix_time,
                tz=validated_timezone,
            )
        except (
            OSError,
            OverflowError,
            ValueError,
        ) as exc:
            raise ResponseFormatError(
                f"{field_name} を日時へ変換できません: {value!r}"
            ) from exc

    iso_string = normalized

    if iso_string.endswith("Z"):
        iso_string = iso_string[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(iso_string)
    except ValueError as exc:
        raise ResponseFormatError(
            f"{field_name} を日時へ変換できません: {value!r}"
        ) from exc

    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=validated_timezone)
    else:
        parsed = parsed.astimezone(validated_timezone)

    return parsed


def _to_float_or_nan(value: object) -> float:
    """
    値を float へ変換する．変換できない場合は NaN を返す．
    """
    if isinstance(value, bool):
        return math.nan

    try:
        return float(value)
    except (TypeError, ValueError):
        return math.nan


def _normalize_channel_value(
    value: object,
) -> float | str | None:
    """
    API のチャンネル値を，数値，文字列，または None に変換する．
    """
    if value is None:
        return None

    if isinstance(value, bool):
        return str(value)

    if isinstance(value, (int, float)):
        return float(value)

    if isinstance(value, str):
        normalized = value.strip()

        if not normalized:
            return None

        try:
            return float(normalized)
        except ValueError:
            return normalized

    return str(value)


def _optional_string(
    value: object,
) -> str | None:
    """
    値を空でない文字列へ変換する．
    """
    if value is None:
        return None

    if not isinstance(value, str):
        value = str(value)

    normalized = value.strip()

    return normalized or None


def _extract_remote_serial(
    data: Mapping[str, Any],
) -> str | None:
    """
    API 応答から機器シリアル番号を取得する．
    """
    for key in _REMOTE_SERIAL_KEYS:
        value = data.get(key)

        if value is None:
            continue

        normalized = _optional_string(value)

        if normalized is not None:
            return normalized

    return None


def _normalize_channel_key(
    value: object,
    *,
    fallback_index: int,
) -> str:
    """
    API 応答中のチャンネル識別子を "ch1" 形式へ正規化する．
    """
    if isinstance(value, bool):
        return f"ch{fallback_index}"

    if isinstance(value, int):
        return f"ch{value}"

    if isinstance(value, float) and value.is_integer():
        return f"ch{int(value)}"

    if isinstance(value, str):
        normalized = value.strip()

        if not normalized:
            return f"ch{fallback_index}"

        if normalized.isdigit():
            return f"ch{normalized}"

        match = _CHANNEL_KEY_PATTERN.fullmatch(normalized)

        if match is not None:
            return f"ch{int(match.group('number'))}"

        return normalized

    return f"ch{fallback_index}"


def _channel_sort_key(
    key: str,
) -> tuple[int, int | str]:
    """
    "ch1"，"ch2" のようなキーを数値順に並べるためのキーを返す．
    """
    match = _CHANNEL_KEY_PATTERN.fullmatch(key)

    if match is None:
        return 1, key

    return 0, int(match.group("number"))


def _parse_channel_mapping(
    channel_data: Mapping[str, Any],
    *,
    fallback_index: int,
) -> ChannelReading:
    """
    current API の channel 要素など，1チャンネル分の Mapping を
    ChannelReading へ変換する．
    """
    key_source: object | None = None

    for candidate_key in (
        "key",
        "channel",
        "channel_no",
        "channel-number",
        "channel_number",
        "num",
        "number",
        "id",
    ):
        if candidate_key in channel_data:
            key_source = channel_data[candidate_key]
            break

    channel_key = _normalize_channel_key(
        key_source,
        fallback_index=fallback_index,
    )

    value: object = None

    for value_key in (
        "value",
        "current",
        "reading",
        "data",
    ):
        if value_key in channel_data:
            value = channel_data[value_key]
            break

    unit: str | None = None

    for unit_key in (
        "unit",
        "unit_string",
        "unit-string",
    ):
        if unit_key in channel_data:
            unit = _optional_string(channel_data[unit_key])
            break

    name: str | None = None

    for name_key in (
        "name",
        "channel_name",
        "channel-name",
        "label",
    ):
        if name_key in channel_data:
            name = _optional_string(channel_data[name_key])
            break

    consumed_keys = {
        "key",
        "channel",
        "channel_no",
        "channel-number",
        "channel_number",
        "num",
        "number",
        "id",
        "value",
        "current",
        "reading",
        "data",
        "unit",
        "unit_string",
        "unit-string",
        "name",
        "channel_name",
        "channel-name",
        "label",
    }

    metadata = {
        key: value
        for key, value in channel_data.items()
        if key not in consumed_keys
    }

    return ChannelReading(
        key=channel_key,
        value=_normalize_channel_value(value),
        unit=unit,
        name=name,
        metadata=metadata,
    )


def _parse_current_channels(
    device: Mapping[str, Any],
) -> tuple[ChannelReading, ...]:
    """
    current API の機器情報からチャンネル一覧を取得する．
    """
    channels_raw: object | None = None

    for key in _CURRENT_CHANNEL_KEYS:
        if key in device:
            channels_raw = device[key]
            break

    if channels_raw is not None:
        channels_sequence = _require_sequence(
            channels_raw,
            field_name="devices[].channel",
        )

        channels: list[ChannelReading] = []

        for index, channel_raw in enumerate(
            channels_sequence,
            start=1,
        ):
            if isinstance(channel_raw, Mapping):
                channels.append(
                    _parse_channel_mapping(
                        _require_mapping(
                            channel_raw,
                            field_name=(
                                f"devices[].channel[{index - 1}]"
                            ),
                        ),
                        fallback_index=index,
                    )
                )
            else:
                channels.append(
                    ChannelReading(
                        key=f"ch{index}",
                        value=_normalize_channel_value(channel_raw),
                    )
                )

        return tuple(channels)

    return _parse_flat_channels(device)


def _find_associated_channel_value(
    data: Mapping[str, Any],
    channel_key: str,
    kind: str,
) -> object | None:
    """
    ch1_unit や ch1-unit のような付随情報を取得する．
    """
    for separator in (
        "_",
        "-",
    ):
        candidate = f"{channel_key}{separator}{kind}"

        if candidate in data:
            return data[candidate]

    return None


def _parse_flat_channel(
    data: Mapping[str, Any],
    *,
    channel_key: str,
) -> ChannelReading:
    """
    data API の ch1，ch2 形式を ChannelReading へ変換する．
    """
    raw_value = data[channel_key]

    if isinstance(raw_value, Mapping):
        channel_mapping = _require_mapping(
            raw_value,
            field_name=channel_key,
        )

        merged = dict(channel_mapping)
        merged.setdefault("key", channel_key)

        return _parse_channel_mapping(
            merged,
            fallback_index=1,
        )

    unit = _optional_string(
        _find_associated_channel_value(
            data,
            channel_key,
            "unit",
        )
    )
    name = _optional_string(
        _find_associated_channel_value(
            data,
            channel_key,
            "name",
        )
    )

    return ChannelReading(
        key=channel_key.lower(),
        value=_normalize_channel_value(raw_value),
        unit=unit,
        name=name,
    )


def _parse_flat_channels(
    data: Mapping[str, Any],
) -> tuple[ChannelReading, ...]:
    """
    Mapping 中の ch1，ch2，... を検出して読み込む．
    """
    channel_keys = [
        key
        for key in data
        if _CHANNEL_KEY_PATTERN.fullmatch(key) is not None
    ]

    channel_keys.sort(key=_channel_sort_key)

    return tuple(
        _parse_flat_channel(
            data,
            channel_key=channel_key,
        )
        for channel_key in channel_keys
    )


def _extract_current_metadata(
    device: Mapping[str, Any],
) -> dict[str, Any]:
    """
    current API の機器情報から主要項目以外をメタデータとして取得する．
    """
    excluded_keys = set(_TIMESTAMP_KEYS)
    excluded_keys.update(_REMOTE_SERIAL_KEYS)
    excluded_keys.update(_CURRENT_CHANNEL_KEYS)

    return {
        key: value
        for key, value in device.items()
        if key not in excluded_keys
    }


def _extract_data_row_metadata(
    row: Mapping[str, Any],
) -> dict[str, Any]:
    """
    data API の1行から主要項目以外をメタデータとして取得する．
    """
    excluded_keys = set(_TIMESTAMP_KEYS)
    excluded_keys.update(_REMOTE_SERIAL_KEYS)
    excluded_keys.update(_CURRENT_CHANNEL_KEYS)

    for key in row:
        if _CHANNEL_KEY_PATTERN.fullmatch(key) is not None:
            excluded_keys.add(key)

            for suffix in _CHANNEL_METADATA_SUFFIXES:
                excluded_keys.add(f"{key}{suffix}")

    return {
        key: value
        for key, value in row.items()
        if key not in excluded_keys
    }


def parse_current_record(
    json_current: Mapping[str, Any],
    *,
    tz: tzinfo = UTC,
    device_index: int = 0,
) -> MeasurementRecord:
    """
    現在値 API の応答から1台分の測定記録を生成する．

    Args:
        json_current:
            get_current() が返す JSON オブジェクト．
        tz:
            返される datetime のタイムゾーン．
            デフォルトは UTC．
        device_index:
            devices 配列のうち，読み取る機器のインデックス．

    Returns:
        MeasurementRecord．

    Raises:
        ResponseFormatError:
            API 応答の構造が想定と異なる場合．
        IndexError:
            device_index が devices の範囲外の場合．
    """
    root = _require_mapping(
        json_current,
        field_name="current response",
    )

    devices_raw = root.get("devices")

    if devices_raw is None:
        raise ResponseFormatError(
            "current response に 'devices' がありません"
        )

    devices = _require_sequence(
        devices_raw,
        field_name="devices",
    )

    if not devices:
        raise ResponseFormatError(
            "current response の devices が空です"
        )

    if isinstance(device_index, bool) or not isinstance(
        device_index,
        int,
    ):
        raise TypeError(
            "device_index には整数を指定してください"
        )

    if not -len(devices) <= device_index < len(devices):
        raise IndexError(
            f"device_index が範囲外です: {device_index} "
            f"(devices={len(devices)})"
        )

    device = _require_mapping(
        devices[device_index],
        field_name=f"devices[{device_index}]",
    )

    timestamp_value = _extract_timestamp_value(
        device,
        field_name=f"devices[{device_index}]",
    )
    timestamp = _parse_timestamp(
        timestamp_value,
        tz=tz,
        field_name=f"devices[{device_index}].unixtime",
    )

    remote_serial = (
        _extract_remote_serial(device)
        or _extract_remote_serial(root)
    )

    channels = _parse_current_channels(device)

    return MeasurementRecord(
        timestamp=timestamp,
        channels=channels,
        remote_serial=remote_serial,
        metadata=_extract_current_metadata(device),
    )


def parse_current_records(
    json_current: Mapping[str, Any],
    *,
    tz: tzinfo = UTC,
) -> list[MeasurementRecord]:
    """
    現在値 API の応答に含まれる全機器を解析する．

    Returns:
        MeasurementRecord のリスト．
    """
    root = _require_mapping(
        json_current,
        field_name="current response",
    )

    devices_raw = root.get("devices")

    if devices_raw is None:
        raise ResponseFormatError(
            "current response に 'devices' がありません"
        )

    devices = _require_sequence(
        devices_raw,
        field_name="devices",
    )

    return [
        parse_current_record(
            root,
            tz=tz,
            device_index=index,
        )
        for index in range(len(devices))
    ]


def _parse_data_row_channels(
    row: Mapping[str, Any],
) -> tuple[ChannelReading, ...]:
    """
    data API の1行からチャンネル一覧を取得する．
    """
    for key in _CURRENT_CHANNEL_KEYS:
        if key not in row:
            continue

        channels_raw = _require_sequence(
            row[key],
            field_name=f"data[].{key}",
        )

        channels: list[ChannelReading] = []

        for index, channel_raw in enumerate(
            channels_raw,
            start=1,
        ):
            if isinstance(channel_raw, Mapping):
                channels.append(
                    _parse_channel_mapping(
                        _require_mapping(
                            channel_raw,
                            field_name=f"data[].{key}[{index - 1}]",
                        ),
                        fallback_index=index,
                    )
                )
            else:
                channels.append(
                    ChannelReading(
                        key=f"ch{index}",
                        value=_normalize_channel_value(channel_raw),
                    )
                )

        return tuple(channels)

    return _parse_flat_channels(row)


def parse_data_records(
    json_data: Mapping[str, Any],
    *,
    tz: tzinfo = UTC,
) -> list[MeasurementRecord]:
    """
    データ取得 API の応答を測定記録のリストへ変換する．

    Args:
        json_data:
            get_data() または get_latest_data() が返す
            JSON オブジェクト．
        tz:
            返される datetime のタイムゾーン．
            デフォルトは UTC．

    Returns:
        MeasurementRecord のリスト．

    Raises:
        ResponseFormatError:
            API 応答の構造が想定と異なる場合．
    """
    root = _require_mapping(
        json_data,
        field_name="data response",
    )

    rows_raw = root.get("data")

    if rows_raw is None:
        raise ResponseFormatError(
            "data response に 'data' がありません"
        )

    rows = _require_sequence(
        rows_raw,
        field_name="data",
    )

    root_remote_serial = _extract_remote_serial(root)
    records: list[MeasurementRecord] = []

    for index, row_raw in enumerate(rows):
        row = _require_mapping(
            row_raw,
            field_name=f"data[{index}]",
        )

        timestamp_value = _extract_timestamp_value(
            row,
            field_name=f"data[{index}]",
        )
        timestamp = _parse_timestamp(
            timestamp_value,
            tz=tz,
            field_name=f"data[{index}].unixtime",
        )

        remote_serial = (
            _extract_remote_serial(row)
            or root_remote_serial
        )

        records.append(
            MeasurementRecord(
                timestamp=timestamp,
                channels=_parse_data_row_channels(row),
                remote_serial=remote_serial,
                metadata=_extract_data_row_metadata(row),
            )
        )

    return records


def _get_temperature_channel(
    record: MeasurementRecord,
) -> ChannelReading | None:
    """
    温度として使用するチャンネルを取得する．

    ch1 が存在すれば ch1 を使用し，存在しなければ先頭の
    チャンネルを使用する．
    """
    channel = record.get_channel("ch1")

    if channel is not None:
        return channel

    if record.channels:
        return record.channels[0]

    return None


def _get_humidity_channel(
    record: MeasurementRecord,
) -> ChannelReading | None:
    """
    湿度として使用するチャンネルを取得する．

    ch2 が存在すれば ch2 を使用し，存在しなければ2番目の
    チャンネルを使用する．
    """
    channel = record.get_channel("ch2")

    if channel is not None:
        return channel

    if len(record.channels) >= 2:
        return record.channels[1]

    return None


def to_temperature_humidity(
    record: MeasurementRecord,
) -> TemperatureHumidityReading:
    """
    汎用 MeasurementRecord を温湿度専用モデルへ変換する．

    ch1 を温度，ch2 を湿度として扱う．
    該当チャンネルがない場合は NaN を使用する．
    """
    if not isinstance(record, MeasurementRecord):
        raise TypeError(
            "record には MeasurementRecord を指定してください"
        )

    temperature_channel = _get_temperature_channel(record)
    humidity_channel = _get_humidity_channel(record)

    temperature = (
        temperature_channel.numeric_value
        if temperature_channel is not None
        else math.nan
    )
    humidity = (
        humidity_channel.numeric_value
        if humidity_channel is not None
        else math.nan
    )

    return TemperatureHumidityReading(
        timestamp=record.timestamp,
        temperature_c=temperature,
        humidity_percent=humidity,
        remote_serial=record.remote_serial,
    )


def parse_current_temperature_humidity(
    json_current: Mapping[str, Any],
    *,
    tz: tzinfo = UTC,
    device_index: int = 0,
) -> TemperatureHumidityReading:
    """
    現在値 API の応答を温湿度専用モデルへ変換する．
    """
    record = parse_current_record(
        json_current,
        tz=tz,
        device_index=device_index,
    )

    return to_temperature_humidity(record)


def parse_temperature_humidity_data(
    json_data: Mapping[str, Any],
    *,
    tz: tzinfo = UTC,
) -> list[TemperatureHumidityReading]:
    """
    データ取得 API の応答を温湿度専用モデルのリストへ変換する．
    """
    records = parse_data_records(
        json_data,
        tz=tz,
    )

    return [
        to_temperature_humidity(record)
        for record in records
    ]


def parse_current(
    json_current: Mapping[str, Any],
    *,
    tz: tzinfo = UTC,
    device_index: int = 0,
) -> tuple[datetime, float, float]:
    """
    現在値から時刻・温度・湿度を抽出する．

    既存 API との互換関数です．

    Returns:
        以下の3要素のタプル．

        - タイムゾーン付き datetime
        - 温度 [°C]
        - 相対湿度 [%]
    """
    reading = parse_current_temperature_humidity(
        json_current,
        tz=tz,
        device_index=device_index,
    )

    return reading.as_tuple()


def parse_data(
    json_data: Mapping[str, Any],
    *,
    tz: tzinfo = UTC,
) -> tuple[
    list[datetime],
    list[float],
    list[float],
]:
    """
    データログから時刻，温度，湿度のリストを生成する．

    既存 API との互換関数です．

    Returns:
        以下の3要素のタプル．

        - datetime のリスト
        - 温度 [°C] のリスト
        - 相対湿度 [%] のリスト
    """
    readings = parse_temperature_humidity_data(
        json_data,
        tz=tz,
    )

    times = [
        reading.timestamp
        for reading in readings
    ]
    temperatures = [
        reading.temperature_c
        for reading in readings
    ]
    humidities = [
        reading.humidity_percent
        for reading in readings
    ]

    return times, temperatures, humidities


__all__ = [
    "parse_current_record",
    "parse_current_records",
    "parse_data_records",
    "to_temperature_humidity",
    "parse_current_temperature_humidity",
    "parse_temperature_humidity_data",
    "parse_current",
    "parse_data",
]