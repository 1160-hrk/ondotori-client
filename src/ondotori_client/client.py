#!/usr/bin/env python3
from __future__ import annotations

"""
client.py

Ondotori WebStorage API クライアント実装

対応デバイスタイプ:
  - "default": TR7A2/7A, TR-7nw/wb/wf, TR4A, TR32B 系列
  - "rtr500": RTR500B 系列

設定は以下のいずれかで注入可能:
  1. 設定ファイルパス (config.json)
  2. 読み込み済み設定辞書 (dict)
  3. 直接認証情報・base_serial を引数で指定
"""
import json
import logging
from typing import Optional, Dict, Any, Tuple, Union, TYPE_CHECKING
import os

if TYPE_CHECKING:
    import pandas as pd
from datetime import datetime

import requests


def parse_current(json_current: Dict[str, Any]) -> Tuple[datetime, float, float]:
    """
    最新の温湿度データから時刻・温度・湿度を抽出する
    """
    devices = json_current.get("devices", [])
    if not devices:
        raise ValueError("No device data in response")
    d = devices[0]
    ts = datetime.fromtimestamp(int(d["unixtime"]))
    ch = d.get("channel", [])
    temp = float(ch[0]["value"]) if len(ch) > 0 else float("nan")
    hum = float(ch[1]["value"]) if len(ch) > 1 else float("nan")
    return ts, temp, hum


def parse_data(json_data: Dict[str, Any]) -> Tuple[list, list, list]:
    """
    データログ JSON から時刻リスト, 温度リスト, 湿度リストを生成する
    """
    rows = json_data.get("data", [])
    times = [datetime.fromtimestamp(int(r["unixtime"])) for r in rows]
    temps = [float(r.get("ch1", float("nan"))) for r in rows]
    hums = [float(r.get("ch2", float("nan"))) for r in rows]
    return times, temps, hums


class OndotoriClient:
    """
    Ondotori WebStorage API クライアント

    コンストラクタ引数:
        config: 設定ファイルパス(str) または 設定辞書(dict)
        api_key, login_id, login_pass, base_serial: 直接指定する場合
        device_type: "default" or "rtr500"
        retries: リトライ回数
        timeout: HTTPリクエストタイムアウト秒
        verbose: デバッグログ出力
        session: カスタム requests.Session
        logger: カスタム logging.Logger
        auto_save_config: 設定を自動保存するかどうか
        config_path: 設定ファイルのパス
    """

    # エンドポイント定義
    _URL_CURRENT = "https://api.webstorage.jp/v1/devices/current"
    _URL_DATA_DEFAULT = "https://api.webstorage.jp/v1/devices/data"
    _URL_DATA_RTR500 = "https://api.webstorage.jp/v1/devices/data-rtr500"
    _URL_LATEST_DEFAULT = "https://api.webstorage.jp/v1/devices/latest-data"
    _URL_LATEST_RTR500 = "https://api.webstorage.jp/v1/devices/latest-data-rtr500"
    _URL_ALERT = "https://api.webstorage.jp/v1/devices/alert"

    def __init__(
        self,
        config: Union[str, Dict[str, Any], None] = None,
        api_key: Optional[str] = None,
        login_id: Optional[str] = None,
        login_pass: Optional[str] = None,
        base_serial: Optional[str] = None,
        device_type: str = "default",
        retries: int = 3,
        timeout: float = 10.0,
        verbose: bool = False,
        session: Optional[requests.Session] = None,
        logger: Optional[logging.Logger] = None,
        auto_save_config: bool = True,
        config_path: str = "config.json",
    ):
        # 設定ロード
        if isinstance(config, str):
            with open(config, encoding="utf-8") as f:
                cfg = json.load(f)
        elif isinstance(config, dict):
            cfg = config
        else:
            cfg = None

        # 認証情報 & 設定辞書セットアップ
        if cfg is not None:
            self._auth = {
                "api-key": cfg["api_key"],
                "login-id": cfg["login_id"],
                "login-pass": cfg["login_pass"],
            }
            self._bases = cfg.get("bases", {})
            self._default_base = cfg.get("default_rtr500_base")
            self._remote_map = cfg.get("remote_map", {})
        else:
            if not all([api_key, login_id, login_pass, base_serial]):
                raise ValueError(
                    "api_key, login_id, login_pass, base_serial が必要です"
                )
            self._auth = {
                "api-key": api_key,
                "login-id": login_id,
                "login-pass": login_pass,
            }
            # 直接指定用の単一ベース
            self._bases = {"default": {"serial": base_serial}}
            self._default_base = "default"
            self._remote_map = {}

        self.device_type = device_type
        self.retries = retries
        self.timeout = timeout

        # HTTP セッション & ヘッダ
        self.session = session or requests.Session()
        self.headers = {
            "Content-Type": "application/json",
            "X-HTTP-Method-Override": "GET",
        }

        # ロガー初期化
        self.logger = logger or logging.getLogger(__name__)
        level = logging.DEBUG if verbose else logging.INFO
        logging.basicConfig(
            level=level, format="%(asctime)s %(levelname)s: %(message)s"
        )

        # 自動保存設定
        self._auto_save_config = auto_save_config
        # どのパスに保存するか — 明示的に文字列パスが渡された場合はそれを尊重
        if isinstance(config, str):
            self._config_path = config
        else:
            self._config_path = config_path

        # config が dict/None から生成された場合、自動で保存
        if self._auto_save_config and (cfg is None or not isinstance(config, str)):
            # 既にファイルが存在する場合は上書きしない（後続で _save_config 呼び出し時に更新）
            if not os.path.exists(self._config_path):
                try:
                    self._save_config()
                except Exception as e:
                    self.logger.warning(
                        "Failed to auto-create config file %s: %s",
                        self._config_path,
                        e,
                    )

    def _resolve_base(self, remote_key: str) -> Optional[str]:
        # リモートキーからベースシリアルを取得
        info = self._remote_map.get(remote_key, {})
        base_name = info.get("base", "")
        base_info = self._bases.get(base_name)
        if not base_info:
            # raise KeyError(f"Base '{base_name}' が設定にありません")
            return info.get("serial")
        return base_info["serial"]

    def _to_timestamp(self, dt: Union[datetime, int, str]) -> int:
        if isinstance(dt, int):
            return dt
        if isinstance(dt, datetime):
            return int(dt.timestamp())
        return int(datetime.fromisoformat(dt).timestamp())

    def _post(self, url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        for attempt in range(self.retries):
            self.logger.debug(
                "POST %s attempt=%s payload_len=%s",
                url,
                attempt + 1,
                len(str(payload)),
            )
            resp = self.session.post(
                url, headers=self.headers, json=payload, timeout=self.timeout
            )
            try:
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                self.logger.warning("Error %s on attempt %s", e, attempt + 1)
                if attempt == self.retries - 1:
                    raise
        # ここには到達しない想定だが、型チェック回避のため例外を送出
        raise RuntimeError("_post: Unexpected exit without response")

    def get_current(self, remote_key: str) -> Dict[str, Any]:
        """現在値取得"""
        serial = self._remote_map.get(remote_key, {}).get("serial", remote_key)
        payload = {**self._auth, "remote-serial": [serial]}
        # デバイスタイプ決定
        device_type_a = self._remote_map.get(remote_key, {}).get(
            "type", self.device_type
            )
        # remote_map へ登録 (base は不要)
        self._update_remote_map(remote_key, serial, device_type_a)
        return self._post(self._URL_CURRENT, payload)

    def get_data(
        self,
        remote_key: str,
        dt_from: Optional[Union[datetime, int, str]] = None,
        dt_to: Optional[Union[datetime, int, str]] = None,
        count: Optional[int] = None,
        hours: Optional[int] = None,
        as_df: bool = False,
        device_type: Optional[str] = None,
    ) -> Union[Dict[str, Any], pd.DataFrame]:
        """期間/件数指定データ取得"""
        # 時間レンジ計算
        if hours is not None:
            now = int(datetime.now().timestamp())
            dt_to_unix = now
            dt_from_unix = now - hours * 3600
        else:
            dt_from_unix = self._to_timestamp(dt_from) if dt_from else None
            dt_to_unix = self._to_timestamp(dt_to) if dt_to else None

        serial = self._remote_map.get(remote_key, {}).get("serial", remote_key)
        payload = {**self._auth, "remote-serial": serial}
        if device_type is not None:
            device_type_a = device_type
        elif self._remote_map.get(remote_key, {}).get("type") is not None:
            device_type_a = self._remote_map[remote_key]["type"]
        else:
            device_type_a = self.device_type
        if device_type_a == "rtr500":
            url = self._URL_DATA_RTR500
            payload["base-serial"] = self._resolve_base(remote_key)
        else:
            url = self._URL_DATA_DEFAULT
            if count is not None:
                payload["number"] = count

        # remote_map 更新
        if device_type_a == "rtr500":
            base_serial_for_map = self._resolve_base(remote_key)
        else:
            base_serial_for_map = None
        self._update_remote_map(
            remote_key, serial, device_type_a, base_serial_for_map
        )

        if dt_from_unix is not None:
            payload["unixtime-from"] = dt_from_unix
        if dt_to_unix is not None:
            payload["unixtime-to"] = dt_to_unix

        result = self._post(url, payload)
        if as_df:
            # DataFrame 出力時にのみインポート
            try:
                import pandas as pd
            except ImportError:
                msg = (
                    "pandas がインストールされていないため DataFrame 出力できません。 "
                    "`pip install ondotori-client[dataframe]` をお試しください。"
                )
                raise ImportError(msg)
            times, temps, hums = parse_data(result)
            return pd.DataFrame(
                {"timestamp": times, "temp_C": temps, "hum_%": hums}
            )
        return result

    def get_latest_data(
        self, remote_key: str, device_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """最新データ取得"""
        serial = self._remote_map.get(remote_key, {}).get("serial", remote_key)
        payload = {**self._auth, "remote-serial": serial}
        if device_type is not None:
            device_type_a = device_type
        elif self._remote_map.get(remote_key, {}).get("type") is not None:
            device_type_a = self._remote_map[remote_key]["type"]
        else:
            device_type_a = self.device_type
        if device_type_a == "rtr500":
            url = self._URL_LATEST_RTR500
            payload["base-serial"] = self._resolve_base(remote_key)
        else:
            url = self._URL_LATEST_DEFAULT
        # remote_map 更新
        if device_type_a == "rtr500":
            base_serial_for_map = self._resolve_base(remote_key)
        else:
            base_serial_for_map = None
        self._update_remote_map(
            remote_key, serial, device_type_a, base_serial_for_map
        )
        return self._post(url, payload)

    def get_alerts(self, remote_key: str) -> Dict[str, Any]:
        """アラートログ取得"""
        serial = self._remote_map.get(remote_key, {}).get("serial", remote_key)
        payload = {**self._auth, "remote-serial": serial}
        payload["base-serial"] = self._resolve_base(remote_key)
        # remote_map 更新（RTR500 前提）
        self._update_remote_map(
            remote_key, serial, "rtr500", payload["base-serial"]
        )
        return self._post(self._URL_ALERT, payload)

    # ------------------------------------------------------------------
    # プライベート: 設定ファイル保存／更新処理
    # ------------------------------------------------------------------

    def _save_config(self) -> None:
        """現在の設定を JSON で保存 (indent=2, UTF-8)"""
        if not self._auto_save_config:
            return
        cfg_out = {
            "api_key": self._auth.get("api-key"),
            "login_id": self._auth.get("login-id"),
            "login_pass": self._auth.get("login-pass"),
            "default_rtr500_base": self._default_base,
            "bases": self._bases,
            "remote_map": self._remote_map,
        }
        try:
            with open(self._config_path, "w", encoding="utf-8") as f:
                json.dump(cfg_out, f, ensure_ascii=False, indent=2)
            self.logger.debug("Config saved to %s", self._config_path)
        except Exception as e:
            self.logger.warning(
                "Failed to save config to %s: %s", self._config_path, e
            )

    def _update_remote_map(
        self,
        remote_key: str,
        serial: str,
        device_type: str,
        base_serial: Optional[str] = None,
    ) -> None:
        """remote_map に情報を追加し、必要なら設定を保存"""
        if not self._auto_save_config:
            return
        if remote_key in self._remote_map:
            return  # 既に登録済み
        info: Dict[str, Any] = {"serial": serial}
        if device_type:
            info["type"] = device_type
        if device_type == "rtr500" and base_serial:
            # base 名は default_rtr500_base を使用
            info["base"] = self._default_base
        self._remote_map[remote_key] = info
        # 保存
        self._save_config()
