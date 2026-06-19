from __future__ import annotations

import math
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from ondotori_client import (
    ResponseFormatError,
    parse_current,
    parse_current_record,
    parse_current_records,
    parse_data,
    parse_data_records,
)


def test_parse_current_compatibility_helper() -> None:
    response = {
        "devices": [
            {
                "serial": "REMOTE_1",
                "unixtime": "1600000000",
                "channel": [
                    {"value": "22.5", "unit": "C"},
                    {"value": "48.0", "unit": "%"},
                ],
            }
        ]
    }

    timestamp, temperature, humidity = parse_current(response)

    assert timestamp == datetime.fromtimestamp(1600000000, tz=timezone.utc)
    assert temperature == 22.5
    assert humidity == 48.0


def test_parse_current_record_preserves_channels_and_metadata() -> None:
    response = {
        "devices": [
            {
                "remote-serial": "REMOTE_1",
                "unixtime": "1600000000",
                "battery": "good",
                "channel": [
                    {
                        "channel": 1,
                        "value": "22.5",
                        "unit": "C",
                        "name": "Temperature",
                        "raw": 100,
                    },
                    {
                        "channel": 2,
                        "value": "48.0",
                        "unit": "%",
                    },
                ],
            }
        ]
    }

    record = parse_current_record(response)

    assert record.remote_serial == "REMOTE_1"
    assert record.require_channel("ch1").numeric_value == 22.5
    assert record.require_channel("ch1").metadata["raw"] == 100
    assert record.metadata["battery"] == "good"


def test_parse_current_records_handles_multiple_devices() -> None:
    response = {
        "devices": [
            {"unixtime": "1", "channel": [{"value": "1"}]},
            {"unixtime": "2", "channel": [{"value": "2"}]},
        ]
    }

    records = parse_current_records(response)

    assert len(records) == 2
    assert records[1].require_channel("ch1").numeric_value == 2.0


def test_parse_data_flat_channels() -> None:
    response = {
        "remote-serial": "REMOTE_1",
        "data": [
            {
                "unixtime": "1600000000",
                "ch1": "21.2",
                "ch1_unit": "C",
                "ch2": "not-a-number",
                "ch2_unit": "%",
                "quality": "ok",
            }
        ],
    }

    records = parse_data_records(response)
    times, temperatures, humidities = parse_data(response)

    assert records[0].remote_serial == "REMOTE_1"
    assert records[0].require_channel("ch1").unit == "C"
    assert records[0].metadata["quality"] == "ok"
    assert times == [datetime.fromtimestamp(1600000000, tz=timezone.utc)]
    assert temperatures == [21.2]
    assert math.isnan(humidities[0])


def test_timezone_conversion() -> None:
    tokyo = ZoneInfo("Asia/Tokyo")
    response = {
        "data": [
            {"unixtime": "0", "ch1": "1", "ch2": "2"},
        ]
    }

    records = parse_data_records(response, tz=tokyo)

    assert records[0].timestamp.hour == 9
    assert records[0].timestamp.utcoffset() is not None


def test_missing_required_fields_raise_response_format_error() -> None:
    with pytest.raises(ResponseFormatError, match="devices"):
        parse_current_record({})

    with pytest.raises(ResponseFormatError, match="data"):
        parse_data_records({})
