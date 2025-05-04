#!/usr/bin/env python3
"""
basic_usage.py

OndotoriClient の利用例
"""
import json
from datetime import datetime

# モジュールをインポート
from ondotori_client.client import OndotoriClient, parse_current, parse_data


def example_with_config():
    """config.json を使った初期化例"""
    # 設定ファイルパスを指定
    client = OndotoriClient(
        config="configs/config.json", device_type="rtr500", verbose=True
    )
    sensor_key = "CrZnS1"

    # 現在値取得
    json_cur = client.get_current(sensor_key)
    ts, temp, hum = parse_current(json_cur)
    print(f"現在値({sensor_key}) - {ts}: {temp:.1f} ℃, {hum:.1f}%")

    # 過去1時間分を DataFrame で取得
    df = client.get_data(sensor_key, hours=1, as_df=True)
    print(df.head())


def example_direct_args():
    """引数直接指定による初期化例"""
    with open("configs/config.json", "r", encoding="utf-8") as f:
        cfg = json.load(f)

    # 直引きモードだけど、値は config.json から
    client = OndotoriClient(
        api_key=cfg["api_key"],
        login_id=cfg["login_id"],
        login_pass=cfg["login_pass"],
        base_serial=cfg["bases"]["Ce302"]["serial"],
        device_type="rtr500",
        verbose=True,
    )
    # リモートシリアル直接指定
    serial = "52BCA065"

    # 最新データ取得
    data = client.get_latest_data(serial)
    count = len(data.get("data", []))
    print(f"最新データ件数: {count}")


if __name__ == "__main__":
    print("=== Example: config.json を使ったモード ===")
    example_with_config()
    print("\n=== Example: 直接引数モード ===")
    example_direct_args()
