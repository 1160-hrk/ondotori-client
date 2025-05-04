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
data_cur = client.get_current("CrZnS1")
ts, temp, hum = parse_current(data_cur)
print(f"現在値: {ts} — {temp}℃ / {hum}%")

# — 2. 過去指定期間のログ取得 —
res = client.get_data("CrZnS1", dt_from="2025-05-01T00:00:00", dt_to="2025-05-02T00:00:00")
times, temps, hums = parse_data(res)
df = pd.DataFrame({"time": times, "temp": temps, "hum": hums})
print(df.head())

# — 3. 直近300件ログ(または hours=1)を DataFrame で —
df_latest = client.get_data("CrZnS1", hours=1, as_df=True)
print(df_latest.tail())

# — 4. アラートログ取得 —
alerts = client.get_alerts("CrZnS1")
print(alerts)

```

## License

MIT © Hiroki Tsusaka