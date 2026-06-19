from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from ondotori_client import (
    ClientConfig,
    ConfigurationError,
    MeasurementRecord,
    OndotoriClient,
    RequestValidationError,
    TemperatureHumidityReading,
)
from ondotori_client.client import parse_current, parse_data


@dataclass
class FakeTransport:
    responses: list[dict[str, Any]]
    calls: list[dict[str, Any]] = field(default_factory=list)
    closed: bool = False

    def post_json(
        self,
        url: str,
        payload: dict[str, Any],
        *,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "url": url,
                "payload": dict(payload),
                "headers": dict(headers or {}),
            }
        )
        return self.responses.pop(0)

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def config_mapping() -> dict[str, object]:
    return {
        "api_key": "KEY",
        "login_id": "ID",
        "login_pass": "PASS",
        "default_rtr500_base": "base-a",
        "bases": {
            "base-a": {"serial": "BASE_A"},
            "base-b": {"serial": "BASE_B"},
        },
        "remote_map": {
            "default-device": {
                "serial": "DEFAULT_SERIAL",
                "type": "default",
            },
            "rtr-device": {
                "serial": "RTR_SERIAL",
                "type": "rtr500",
                "base": "base-b",
            },
        },
    }


def test_compatibility_parsers_are_importable_from_client_module() -> None:
    current = {
        "devices": [
            {
                "unixtime": "0",
                "channel": [{"value": "1"}, {"value": "2"}],
            }
        ]
    }
    data = {"data": [{"unixtime": "0", "ch1": "1", "ch2": "2"}]}

    assert parse_current(current)[1:] == (1.0, 2.0)
    assert parse_data(data)[1:] == ([1.0], [2.0])


def test_get_current_uses_remote_alias(
    config_mapping: dict[str, object],
) -> None:
    response = {
        "devices": [
            {
                "unixtime": "0",
                "channel": [{"value": "20"}, {"value": "50"}],
            }
        ]
    }
    transport = FakeTransport([response])
    client = OndotoriClient(config_mapping, transport=transport)

    assert client.get_current("default-device") == response
    call = transport.calls[0]
    assert call["url"] == client._URL_CURRENT
    assert call["payload"]["remote-serial"] == ["DEFAULT_SERIAL"]
    assert call["payload"]["api-key"] == "KEY"


def test_get_current_typed_helpers(
    config_mapping: dict[str, object],
) -> None:
    response = {
        "devices": [
            {
                "unixtime": "0",
                "channel": [{"value": "20"}, {"value": "50"}],
            }
        ]
    }
    transport = FakeTransport([response, response])
    client = OndotoriClient(config_mapping, transport=transport)

    record = client.get_current_record("default-device")
    reading = client.get_current_temperature_humidity("default-device")

    assert isinstance(record, MeasurementRecord)
    assert isinstance(reading, TemperatureHumidityReading)
    assert reading.temperature_c == 20.0


def test_get_data_default_payload(
    config_mapping: dict[str, object],
) -> None:
    transport = FakeTransport([{"data": []}])
    client = OndotoriClient(config_mapping, transport=transport)

    client.get_data(
        "default-device",
        dt_from="1970-01-01T00:00:00+00:00",
        dt_to=60,
        count=10,
    )

    call = transport.calls[0]
    assert call["url"] == client._URL_DATA_DEFAULT
    assert call["payload"]["remote-serial"] == "DEFAULT_SERIAL"
    assert call["payload"]["unixtime-from"] == 0
    assert call["payload"]["unixtime-to"] == 60
    assert call["payload"]["number"] == 10
    assert "base-serial" not in call["payload"]


def test_get_data_rtr500_payload(
    config_mapping: dict[str, object],
) -> None:
    transport = FakeTransport([{"data": []}])
    client = OndotoriClient(config_mapping, transport=transport)

    client.get_data("rtr-device", dt_from=0, dt_to=60)

    call = transport.calls[0]
    assert call["url"] == client._URL_DATA_RTR500
    assert call["payload"]["remote-serial"] == "RTR_SERIAL"
    assert call["payload"]["base-serial"] == "BASE_B"


def test_unknown_key_is_treated_as_serial(
    config_mapping: dict[str, object],
) -> None:
    transport = FakeTransport([{"data": []}])
    client = OndotoriClient(config_mapping, transport=transport)

    client.get_data("DIRECT_SERIAL", count=1)

    assert transport.calls[0]["payload"]["remote-serial"] == "DIRECT_SERIAL"


def test_unknown_rtr500_uses_default_base(
    config_mapping: dict[str, object],
) -> None:
    transport = FakeTransport([{"data": []}])
    client = OndotoriClient(config_mapping, transport=transport)

    client.get_data("DIRECT_RTR", device_type="rtr500")

    assert transport.calls[0]["payload"]["base-serial"] == "BASE_A"


def test_rtr500_without_base_is_rejected() -> None:
    config = ClientConfig.from_credentials(
        api_key="A",
        login_id="B",
        login_pass="C",
    )
    client = OndotoriClient(
        config,
        transport=FakeTransport([{"data": []}]),
    )

    with pytest.raises(ConfigurationError, match="親機"):
        client.get_data("SERIAL", device_type="rtr500")


def test_invalid_time_arguments_are_rejected(
    config_mapping: dict[str, object],
) -> None:
    client = OndotoriClient(
        config_mapping,
        transport=FakeTransport([{"data": []}]),
    )

    with pytest.raises(RequestValidationError, match="同時"):
        client.get_data("default-device", hours=1, dt_from=0)

    with pytest.raises(RequestValidationError, match="正の"):
        client.get_data("default-device", hours=0)

    with pytest.raises(RequestValidationError, match="開始日時"):
        client.get_data("default-device", dt_from=10, dt_to=0)


def test_count_is_not_allowed_for_rtr500(
    config_mapping: dict[str, object],
) -> None:
    client = OndotoriClient(
        config_mapping,
        transport=FakeTransport([{"data": []}]),
    )

    with pytest.raises(RequestValidationError, match="count"):
        client.get_data("rtr-device", count=1)


def test_get_data_records(
    config_mapping: dict[str, object],
) -> None:
    response = {
        "data": [
            {"unixtime": "0", "ch1": "21.0", "ch2": "45.0"},
        ]
    }
    client = OndotoriClient(
        config_mapping,
        transport=FakeTransport([response]),
        default_timezone=timezone.utc,
    )

    records = client.get_data_records("default-device", count=1)

    assert records[0].timestamp == datetime(1970, 1, 1, tzinfo=timezone.utc)
    assert records[0].require_channel("ch1").numeric_value == 21.0


def test_get_data_frame(
    config_mapping: dict[str, object],
) -> None:
    pytest.importorskip("pandas")
    response = {
        "data": [
            {"unixtime": "0", "ch1": "21.0", "ch2": "45.0"},
        ]
    }
    client = OndotoriClient(
        config_mapping,
        transport=FakeTransport([response]),
    )

    frame = client.get_data_frame("default-device", count=1)

    assert list(frame.columns) == ["timestamp", "temp_C", "hum_%"]
    assert frame.loc[0, "temp_C"] == 21.0


def test_get_alerts_forces_rtr500_endpoint(
    config_mapping: dict[str, object],
) -> None:
    transport = FakeTransport([{"alerts": []}])
    client = OndotoriClient(config_mapping, transport=transport)

    assert client.get_alerts("rtr-device") == {"alerts": []}
    assert transport.calls[0]["url"] == client._URL_ALERT
    assert transport.calls[0]["payload"]["base-serial"] == "BASE_B"


def test_explicit_config_save(
    tmp_path: Path,
    config_mapping: dict[str, object],
) -> None:
    client = OndotoriClient(
        config_mapping,
        transport=FakeTransport([]),
    )
    path = tmp_path / "config.json"

    assert client.save_config(path) == path
    assert path.exists()


def test_external_transport_is_not_closed_by_client(
    config_mapping: dict[str, object],
) -> None:
    transport = FakeTransport([])
    client = OndotoriClient(config_mapping, transport=transport)

    client.close()

    assert transport.closed is False
    with pytest.raises(RuntimeError, match="閉じられています"):
        client.get_current("default-device")
