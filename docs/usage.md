# 使用例: OndotoriClient クラス

このドキュメントでは、`OndotoriClient` クラスの使用方法について説明します。`OndotoriClient` は、Ondotori WebStorage API を使用して、さまざまなデバイスから温湿度データを取得するための Python クライアントです。

## クライアントの初期化

`OndotoriClient` クラスのインスタンスを作成するためには、以下の方法で設定を指定することができます。

### 1. `config.json` を使用する方法

`config.json` 設定ファイルを使用することで、API キーやログイン情報、接続先の設定を外部ファイルから読み込むことができます。

```python
from ondotori_client.client import OndotoriClient, parse_current, parse_data

# 設定ファイルを指定してクライアントを初期化
client = OndotoriClient(config="path-to-config/config.json", device_type="rtr500", verbose=True)

# 現在値を取得
sensor_key = "config.jsonで指定したremote_mapのキー"
json_cur = client.get_current(sensor_key)
ts, temp, hum = parse_current(json_cur)
print(f"現在値({sensor_key}) - {ts}: {temp:.1f} ℃, {hum:.1f}%")

# 過去1時間分のデータを DataFrame で取得
df = client.get_data(sensor_key, hours=1, as_df=True)
print(df.head())
```

### 2. 直接引数を指定する方法

設定ファイルを使わず、クライアントの初期化時に直接引数を指定する方法もあります。

```python
from ondotori_client.client import OndotoriClient, parse_current, parse_data
import json

# 設定ファイルを読み込み、直接引数でクライアントを初期化
with open("configs/config.json", "r", encoding="utf-8") as f:
    cfg = json.load(f)

client = OndotoriClient(
    api_key=cfg["api_key"],
    login_id=cfg["login_id"],
    login_pass=cfg["login_pass"],
    base_serial=cfg["bases"]["Ce302"]["serial"],
    device_type="rtr500",
    verbose=True
)

# 最新データを取得
serial = "52BCA065"
data = client.get_latest_data(serial)
count = len(data.get("data", []))
print(f"最新データ件数: {count}")
```

### 3. データの取得と処理

以下のメソッドを使用して、さまざまなデータを取得し、処理することができます。

#### 現在値の取得

```python
# 現在の温湿度データを取得
json_cur = client.get_current("CrZnS1")
ts, temp, hum = parse_current(json_cur)
print(f"現在値: {ts} → {temp:.1f} °C, {hum:.1f}%")
```

#### 過去のデータの取得

```python
# 過去1時間分のデータを取得
json_data = client.get_data("CrZnS1", hours=1, as_df=False)
times, temps, hums = parse_data(json_data)
df = pd.DataFrame({"time": times, "temp": temps, "hum": hums})
print(df.head())
```

#### 最新データの取得

```python
# 直近の300件のデータを取得
df_latest = client.get_data("CrZnS1", hours=1, as_df=True)
print(df_latest.tail())
```

#### アラートログの取得

```python
# アラートログを取得
alerts = client.get_alerts("CrZnS1")
print(alerts)
```

### 4. グラフ表示 (オプション)

過去のデータを時系列でグラフ表示することもできます。以下はその一例です。

```python
import matplotlib.pyplot as plt

# データの取得
json_data = client.get_data("CrZnS1", dt_from="2025-05-01T00:00:00", dt_to="2025-05-02T00:00:00", as_df=False)
times, temps, hums = parse_data(json_data)

# グラフ描画
fig, ax = plt.subplots(figsize=(10, 5))
ax.plot(times, temps, label="Temperature (°C)")
ax.set_xlabel("Time")
ax.set_ylabel("Temperature (°C)")
ax.tick_params(axis='x', rotation=45)

ax2 = ax.twinx()
ax2.plot(times, hums, label="Humidity (%)", linestyle='--')
ax2.set_ylabel("Humidity (%)")
plt.show()
```

## 詳細な使い方

さらに高度なオプションや内部挙動を知りたい場合は、[`docs/usage_advanced.md`](usage_advanced.md) を参照してください。

## 結論

このライブラリは、Ondotori WebStorage API を介してデバイスから温湿度データを簡単に取得し、さまざまな形式でデータを処理することができます。上記の例を参考にして、`OndotoriClient` を使用したアプリケーションを開発できます。
