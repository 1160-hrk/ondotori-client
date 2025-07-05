# Ondotori Client 詳細ガイド（Advanced Usage）

本ドキュメントでは `src/ondotori_client/client.py` に実装されている **OndotoriClient** と補助関数 **parse_current / parse_data** のすべての機能と使い方を解説します。
---

## 目次
1. 概要
2. インストール方法
3. クライアント初期化
   1. `config.json` を用いる方法
   2. 直接引数で指定する方法
   3. 共通オプション（`retries` / `timeout` / `verbose` など）
4. デバイス種別 (`device_type`) と自動判定ロジック
5. ベース・リモートマップの仕組み
6. メソッドリファレンス
   1. `get_current()`
   2. `get_data()`
   3. `get_latest_data()`
   4. `get_alerts()`
7. 補助関数
   1. `parse_current()`
   2. `parse_data()`
8. 高度な使い方
   1. `requests.Session` の差し替え
   2. カスタムロガーの注入
   3. pandas DataFrame 出力オプション
9. エラーハンドリングと例外
10. よくある質問 (FAQ)
11. ライセンス

---

## 1. 概要

`OndotoriClient` は、T&D 社「おんどとり WebStorage API」（REST API）を Python から簡単に操作するためのクライアントライブラリです。対応デバイスタイプは以下の 2 系統です。

| デバイスタイプ | 値 (`device_type`) | 対応シリーズ |
| --- | --- | --- |
| デフォルト | `"default"` | TR7A2/7A, TR-7nw/wb/wf, TR4A, TR32B 等 |
| RTR500B 系 | `"rtr500"` | RTR500B + 各種リモートセンサ |

---

## 2. インストール方法
```bash
pip install ondotori-client
# DataFrame 出力が必要な場合 (pandas 付き)
pip install "ondotori-client[dataframe]"
```

---

## 3. クライアント初期化
`OndotoriClient` のインスタンス化には **設定ファイル方式** と **直接引数方式** の 2 通りがあります。

### 3.1 `config.json` を用いる方法
```python
from ondotori_client.client import OndotoriClient

client = OndotoriClient(
    config="config.json",   # 例: プロジェクト直下に配置
    device_type="rtr500",   # 省略時は "default"
    verbose=True             # デバッグログを標準出力に
)
```

#### `config.json` に含められる主なキー
| キー | 必須 | 説明 |
| --- | --- | --- |
| `api_key` | ○ | APIキー |
| `login_id`, `login_pass` | ○ | WebStorage のログイン資格情報 |
| `default_rtr500_base` | △ | RTR500 系のみ。ベース親機のデフォルト名 |
| `bases` | △ | 複数ベースを扱う場合のマッピングテーブル |
| `remote_map` | △ | センサー名 → シリアル番号 等のマップ |

> **ヒント**: `remote_map` のキーは自由に命名できます。メソッド呼び出し時はこのキーを `remote_key` として渡します。

### 3.2 直接引数で指定する方法
```python
client = OndotoriClient(
    api_key="YOUR_API_KEY",
    login_id="user@example.com",
    login_pass="********",
    base_serial="BASE_SERIAL_IF_RTR500",
    device_type="default",  # RTR500の場合は "rtr500"
    retries=5,               # → 既定: 3
    timeout=15.0,            # → 既定: 10.0 秒
)
```

### 3.3 共通オプション
| パラメータ | 型 | 既定値 | 説明 |
| --- | --- | --- | --- |
| `retries` | `int` | `3` | HTTP エラー時のリトライ回数 |
| `timeout` | `float` | `10.0` | HTTP リクエストのタイムアウト（秒） |
| `verbose` | `bool` | `False` | `True` の場合、`logging.DEBUG` レベルでコンソール出力 |
| `session` | `requests.Session` | `None` | カスタムセッションを指定可 |
| `logger` | `logging.Logger` | `None` | 既存ロガーを流用する場合に指定 |

---

## 4. デバイス種別 (`device_type`) と自動判定ロジック
コンストラクタで指定した `device_type` はメソッド呼び出し時の既定値になりますが、**個別のセンサーごとに `remote_map` 内で `type` を上書き**することも可能です。

```json
"remote_map": {
  "Freezer01": { "serial": "A1234567", "type": "default" },
  "Warehouse": { "serial": "B7654321", "type": "rtr500", "base": "MainBase" }
}
```

メソッド側で `device_type` 引数を明示すればさらに上書き可能で、優先順位は次の通りです。

```
個別引数 (device_type) > remote_map.type > クライアント既定値
```

---

## 5. ベース・リモートマップの仕組み
RTR500 系デバイスでは **ベース親機のシリアル番号** が必要です。`OndotoriClient` は以下の手順でベースシリアルを解決します。

1. `remote_map[remote_key]["base"]` があれば、その名前で `bases` を引く
2. なければ `default_rtr500_base` を使用
3. それでも見つからなければエラー (`KeyError`) が投げられます

---

## 6. メソッドリファレンス

### 6.1 `get_current(remote_key)`
**説明**: センサーの「現在値」(最新 1 件) を取得します。

```python
json_cur = client.get_current("Freezer01")
ts, temp, hum = parse_current(json_cur)
print(f"{ts}: {temp:.1f}℃ / {hum:.1f}%")
```

| 引数 | 型 | 必須 | 説明 |
| --- | --- | --- | --- |
| `remote_key` | `str` | ○ | `remote_map` のキー、またはシリアル番号 |

返り値は **JSON ディクショナリ**。温湿度 (CH1/CH2) しか無い機種にも対応しています。

---

### 6.2 `get_data(remote_key, ...)`
**説明**: 過去データを件数・期間・時間幅など柔軟に指定して取得します。

```python
# (A) 直近 300 件（デフォルト）
json_data = client.get_data("Freezer01")

# (B) 特定の日時範囲を ISO8601 文字列で
json_data = client.get_data("Freezer01", dt_from="2025-01-01T00:00:00", dt_to="2025-01-02T00:00:00")

# (C) 過去 n 時間分を pandas.DataFrame で
import pandas as pd
df = client.get_data("Freezer01", hours=6, as_df=True)
```

| 引数 | 型 | 既定値 | 説明 |
| --- | --- | --- | --- |
| `dt_from` / `dt_to` | `datetime` / `int` / `str` | `None` | 期間指定。型は UNIX 時間・datetime・ISO8601 文字列いずれも可 |
| `count` | `int` | `None` | デフォルト系のみ有効。取得件数を直接指定 |
| `hours` | `int` | `None` | 現在時刻から遡る時間幅（時間） |
| `as_df` | `bool` | `False` | `True` で `pandas.DataFrame` を返す |
| `device_type` | `str` | `None` | 優先的にデバイスタイプを上書き |

> `hours` を指定すると `dt_from` `dt_to` は無視されます。

---

### 6.3 `get_latest_data(remote_key, device_type=None)`
**説明**: API が保持する **最新 300 件** (RTR500 系も同様) を取得します。`get_data(..., count=300)` に相当しますがエンドポイントが異なります。

```python
latest = client.get_latest_data("Warehouse")
print(len(latest["data"]))  # → 最大 300
```

---

### 6.4 `get_alerts(remote_key)`
**説明**: アラートログ（上限 1,000 件）を取得します。

```python
alerts = client.get_alerts("Warehouse")
for row in alerts.get("alert", []):
    print(row)
```

RTR500 系以外でも利用可能ですが、ベースシリアル解決の挙動は RTR500 と同じです。

---

## 7. 補助関数

### 7.1 `parse_current(json_current)`
| 戻り値 | 型 |
| --- | --- |
| `timestamp` | `datetime.datetime` |
| `temp_C` | `float` |
| `hum_%` | `float` |

内部では JSON 構造 `json_current["devices"][0]` から以下を抜き出しています。

```python
unixtime -> datetime
channel[0]["value"] -> 温度
channel[1]["value"] -> 湿度
```

### 7.2 `parse_data(json_data)`
返り値は `(times, temps, hums)` の 3 要素リスト。pandas 未使用で軽量に扱いたい場合に便利です。

---

## 8. 高度な使い方

### 8.1 `requests.Session` の差し替え
```python
import requests
session = requests.Session()
session.proxies.update({"https": "http://proxy.example.com:8080"})
client = OndotoriClient(config="config.json", session=session)
```

### 8.2 カスタムロガーの注入
```python
import logging
logger = logging.getLogger("ondotori")
logger.setLevel(logging.DEBUG)
client = OndotoriClient(config="config.json", logger=logger)
```

### 8.3 pandas DataFrame 出力
`as_df=True` & `pip install pandas` が前提です。カラムは `timestamp`, `temp_C`, `hum_%` 固定。

---

## 9. エラーハンドリングと例外
- **`ValueError`**: 設定不足 (`api_key` 等) やレスポンスにデータが無い場合
- **`KeyError`**: `base_serial` が解決できない場合
- **`requests.exceptions.HTTPError`**: ステータスコード 4xx/5xx
- **`ImportError`**: `as_df=True` かつ pandas 未インストール

`retries` 回だけ自動リトライを行い、それでも失敗すると最後の例外を送出します。

---

## 10. よくある質問 (FAQ)
**Q1. TR7A と RTR-500 を混在させられますか?**  
A. 可能です。`remote_map` でそれぞれ `type` を指定してください。

**Q2. CSV で保存したい**  
A. `df.to_csv("file.csv", index=False)` をお試しください。

**Q3. API 呼び出し上限に達したら?**  
A. WebStorage の仕様上、短時間に大量リクエストすると `429` となります。`retries` を増やすか、`time.sleep()` で間隔を開けてください。

---

## 11. ライセンス
MIT © Hiroki Tsusaka 