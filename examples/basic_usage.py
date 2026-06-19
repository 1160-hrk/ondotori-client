#!/usr/bin/env python3
"""
basic_usage.py

OndotoriClient の基本的な利用例．

実行前に，実際の認証情報と機器情報を設定した
configs/config.json を用意してください．
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from ondotori_client import OndotoriClient, parse_current


CONFIG_PATH = Path("configs/config.json")
JST = ZoneInfo("Asia/Tokyo")


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    """JSON 設定ファイルを辞書として読み込む．"""
    with path.open(encoding="utf-8") as file:
        config = json.load(file)

    if not isinstance(config, dict):
        raise ValueError(
            f"設定ファイルのルートは JSON オブジェクトである必要があります: "
            f"{path}"
        )

    return config


def example_with_config() -> None:
    """config.json を使ってクライアントを初期化する例．"""
    sensor_key = "CrZnS1"

    with OndotoriClient.from_file(
        CONFIG_PATH,
        device_type="rtr500",
        default_timezone=JST,
        verbose=True,
    ) as client:
        # 現在値を生の JSON として取得する．
        json_current = client.get_current(sensor_key)

        # ch1 を温度，ch2 を湿度として解析する．
        timestamp, temperature, humidity = parse_current(
            json_current,
            tz=JST,
        )

        print(
            f"現在値（{sensor_key}）－{timestamp}: "
            f"{temperature:.1f} ℃，{humidity:.1f} %"
        )

        # 過去1時間分の温湿度データを DataFrame として取得する．
        dataframe = client.get_data_frame(
            sensor_key,
            hours=1,
        )

        print("\n過去1時間のデータ:")
        print(dataframe.head())


def example_direct_args() -> None:
    """認証情報を引数で直接指定して初期化する例．"""
    config = load_config()

    default_base_name = config.get("default_rtr500_base")

    if not isinstance(default_base_name, str) or not default_base_name:
        raise ValueError(
            "config.json に default_rtr500_base が設定されていません"
        )

    bases = config.get("bases")

    if not isinstance(bases, dict):
        raise ValueError(
            "config.json の bases は JSON オブジェクトである必要があります"
        )

    base_config = bases.get(default_base_name)

    if not isinstance(base_config, dict):
        raise ValueError(
            f"default_rtr500_base={default_base_name!r} に対応する"
            "親機設定が bases にありません"
        )

    base_serial = base_config.get("serial")

    if not isinstance(base_serial, str) or not base_serial:
        raise ValueError(
            f"親機 {default_base_name!r} に serial が設定されていません"
        )

    api_key = config.get("api_key")
    login_id = config.get("login_id")
    login_pass = config.get("login_pass")

    if not isinstance(api_key, str) or not api_key:
        raise ValueError("config.json に api_key が設定されていません")

    if not isinstance(login_id, str) or not login_id:
        raise ValueError("config.json に login_id が設定されていません")

    if not isinstance(login_pass, str) or not login_pass:
        raise ValueError("config.json に login_pass が設定されていません")

    # remote_map を使わず，API にリモートシリアルを直接渡す．
    remote_serial = "52BCA065"

    with OndotoriClient.from_credentials(
        api_key=api_key,
        login_id=login_id,
        login_pass=login_pass,
        base_serial=base_serial,
        device_type="rtr500",
        default_timezone=JST,
        verbose=True,
    ) as client:
        latest_data = client.get_latest_data(remote_serial)

        data_rows = latest_data.get("data", [])

        if not isinstance(data_rows, list):
            raise ValueError(
                "API 応答の data がリストではありません"
            )

        print(f"最新データ件数: {len(data_rows)}")


def main() -> None:
    """各利用例を順番に実行する．"""
    print("=== Example: config.json を使ったモード ===")
    example_with_config()

    print("\n=== Example: 直接引数モード ===")
    example_direct_args()


if __name__ == "__main__":
    main()