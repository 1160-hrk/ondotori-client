from __future__ import annotations

import json

import pytest

from ondotori_client import ClientConfig, ConfigurationError


@pytest.fixture
def config_mapping() -> dict[str, object]:
    return {
        "api_key": "API_KEY",
        "login_id": "LOGIN_ID",
        "login_pass": "LOGIN_PASS",
        "default_rtr500_base": "base-a",
        "bases": {
            "base-a": {"serial": "BASE_SERIAL_A"},
            "base-b": {"serial": "BASE_SERIAL_B"},
        },
        "remote_map": {
            "room": {
                "serial": "DEFAULT_REMOTE",
                "type": "default",
            },
            "freezer": {
                "serial": "RTR_REMOTE",
                "type": "rtr500",
                "base": "base-b",
            },
            "lab": {
                "serial": "RTR_DEFAULT_BASE_REMOTE",
                "type": "rtr500",
            },
        },
    }


def test_from_mapping_builds_typed_config(
    config_mapping: dict[str, object],
) -> None:
    config = ClientConfig.from_mapping(config_mapping)

    assert config.credentials.login_id == "LOGIN_ID"
    assert config.bases["base-a"].serial == "BASE_SERIAL_A"
    assert config.remotes["freezer"].device_type == "rtr500"
    assert config.remotes["freezer"].base == "base-b"
    assert config.remotes["lab"].base is None


def test_secret_values_are_not_in_credentials_repr(
    config_mapping: dict[str, object],
) -> None:
    config = ClientConfig.from_mapping(config_mapping)
    representation = repr(config.credentials)

    assert "API_KEY" not in representation
    assert "LOGIN_PASS" not in representation
    assert "LOGIN_ID" in representation


def test_invalid_base_reference_is_rejected(
    config_mapping: dict[str, object],
) -> None:
    remote_map = config_mapping["remote_map"]
    assert isinstance(remote_map, dict)
    freezer = remote_map["freezer"]
    assert isinstance(freezer, dict)
    freezer["base"] = "missing"

    with pytest.raises(ConfigurationError, match="存在しない親機"):
        ClientConfig.from_mapping(config_mapping)


def test_default_device_cannot_have_base(
    config_mapping: dict[str, object],
) -> None:
    remote_map = config_mapping["remote_map"]
    assert isinstance(remote_map, dict)
    room = remote_map["room"]
    assert isinstance(room, dict)
    room["base"] = "base-a"

    with pytest.raises(ConfigurationError, match="base は指定できません"):
        ClientConfig.from_mapping(config_mapping)


def test_rtr500_requires_base(
    config_mapping: dict[str, object],
) -> None:
    config_mapping["default_rtr500_base"] = None
    remote_map = config_mapping["remote_map"]
    assert isinstance(remote_map, dict)
    lab = remote_map["lab"]
    assert isinstance(lab, dict)
    lab.pop("base", None)

    with pytest.raises(ConfigurationError, match="親機が設定されていません"):
        ClientConfig.from_mapping(config_mapping)


def test_from_file_and_explicit_save(
    tmp_path,
    config_mapping: dict[str, object],
) -> None:
    source = tmp_path / "source.json"
    source.write_text(
        json.dumps(config_mapping, ensure_ascii=False),
        encoding="utf-8",
    )

    config = ClientConfig.from_file(source)
    destination = tmp_path / "saved.json"
    returned_path = config.save(destination)

    assert returned_path == destination
    assert ClientConfig.from_file(destination) == config

    with pytest.raises(ConfigurationError, match="既に存在"):
        config.save(destination)

    config.save(destination, overwrite=True)
