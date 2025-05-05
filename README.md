# ondotori-client

[![CI](https://github.com/1160-hrk/ondotori-client/actions/workflows/ci.yml/badge.svg)](https://github.com/1160-hrk/ondotori-client/actions)
[![PyPI version](https://img.shields.io/pypi/v/ondotori-client.svg)](https://pypi.org/project/ondotori-client/)
[![License](https://img.shields.io/github/license/1160-hrk/ondotori-client.svg)](https://github.com/1160-hrk/ondotori-client/blob/main/LICENSE)


## 概要

Ondotori WebStorage API（RTR500B／その他機種）を Python から簡単に操作するクライアントライブラリです。

## インストール

```bash
pip install ondotori-client
````

## Quickstart

### DataFrame 出力を使う場合

```bash
pip install ondotori-client[dataframe]
```

### 典型的な使い方

```python
from ondotori_client.client import OndotoriClient, parse_current, parse_data
import pandas as pd

# — 設定ファイルを使う場合 —
client = OndotoriClient(config="config.example.json", device_type="rtr500", verbose=True)

# — 1. 現在値取得 —
data_cur = client.get_current("<remote_serial_key or remote_serial>")
ts, temp, hum = parse_current(data_cur)
print(f"現在値: {ts} — {temp}℃ / {hum}%")

# — 2. 過去指定期間のログ取得 —
res = client.get_data("<remote_serial_key or remote_serial>", dt_from="2025-05-01T00:00:00", dt_to="2025-05-02T00:00:00")
times, temps, hums = parse_data(res)
df = pd.DataFrame({"time": times, "temp": temps, "hum": hums})
print(df.head())

# — 3. 直近300件ログ(または hours=1)を DataFrame で —
df_latest = client.get_data("<remote_serial_key or remote_serial>", hours=1, as_df=True)
print(df_latest.tail())

# — 4. アラートログ取得 —
alerts = client.get_alerts("<remote_serial_key or remote_serial>")
print(alerts)

```

## `config.json` 設定ファイル

`config.json` は、システムの設定を定義するファイルです。このファイルには、APIの認証情報、基本情報、接続するセンサーの設定などが含まれています。以下に、`config.json` の構造と各項目の説明を示します。

### 設定例 (`config.example.json`)

```json
{
    "api_key": "<YOUR_API_KEY>",
    "login_id": "<YOUR_LOGIN_ID>",
    "login_pass": "<YOUR_LOGIN_PASSWORD>",
  
    "default_rtr500_base": "name_base1",
  
    "bases": {
      "name_base1": {
        "serial": "<YOUR_BASE_SERIAL_FOR_BASE1>"
      }
    },
  
    "remote_map": {
      "name1_rtr500":   { "serial": "name1_rtr500",  "type": "rtr500",  "base": "BASE1" },
      "name2_rtr500":   { "serial": "name2_rtr500",  "type": "rtr500",  "base": "BASE1" },
      "name3_rtr500":   { "serial": "name3_rtr500",  "type": "rtr500",  "base": "BASE1" },
  
      "name1_default":  { "serial": "name1_default", "type": "default" },
      "name2_default":  { "serial": "name2_default", "type": "default" }
    }
}
```

### 各項目の説明

* **`api_key`**: 必須のAPIキー。サービスにアクセスするために使用されます。（[公式ページ](https://ondotori.webstorage.jp/docs/api/authentication/auth_apikey.html)をご参照ください。）

* **`login_id`** と **`login_pass`**: Ondotori Web StrageのユーザーのログインIDとパスワード。これらを使用して、サービスにログインします。

* **`default_rtr500_base`**: デフォルトで使用するベースの名前。（RTR500Bを使用する時のみ必要）

* **`bases`**: 使用するベースの設定。ここでは、`name_base1` のような名前のベースと、そのシリアル番号を指定します。（RTR500Bを使用する時のみ必要）

* **`remote_map`**: 各センサーとその設定をマッピングするための部分です。`name1_rtr500` のようなセンサー名に対して、シリアル番号、タイプ、ベースを設定します。
  * ```key```: センサーの名前（自由に設定して構いません。```OndotoriClient```のインスタンスメソッドの引数に使います。）
  * ```serial```: シリアル番号（OndotoriのWeb Strageの[機器設定](https://ondotori.webstorage.jp/device/)にて確認できます。）
  * ```base```: RTR500Bを使用する時のみその親機の名前を設定します。（上記で設定した```bases```の中から選んでください。指定しないと```default_rtr500_base```で設定したものが使用されます。）

### 使用方法

1. **`config.example.json`** をコピーして、`config.json` ファイルを作成します。
2. 必要な設定（APIキー、ログイン情報、ベースやセンサー情報）を **`config.json`** に記入します。
3. `config.json` をプロジェクトのルートディレクトリに配置してください。

## License

MIT © Hiroki Tsusaka