# API Reference

## OndotoriClient クラス

`OndotoriClient`クラスは、Ondotori WebStorage APIにアクセスするためのクライアントです。設定ファイル（`config.json`）または直接指定された引数を使用して、認証情報や接続設定を管理します。

### コンストラクタ引数

* **config** (`str`, `dict`, `None`): 設定ファイルパス（`config.json`）または設定辞書（`dict`）を指定します。どちらも使用可能です。設定が指定されていない場合、以下の引数を直接指定する必要があります。
* **api\_key** (`str`): Ondotori WebStorage APIのAPIキー。
* **login\_id** (`str`): Ondotori WebStorage APIのログインID。
* **login\_pass** (`str`): Ondotori WebStorage APIのログインパスワード。
* **base\_serial** (`str`): Ondotoriデバイスの親機のシリアル番号。
* **device\_type** (`str`): デバイスタイプの指定（"default" または "rtr500"）。デフォルトは "default"。
* **retries** (`int`): リトライ回数。デフォルトは3回。
* **timeout** (`float`): HTTPリクエストのタイムアウト秒。デフォルトは10秒。
* **verbose** (`bool`): デバッグログを表示するかどうか。デフォルトは`False`。
* **session** (`requests.Session`): カスタムのHTTPセッションオブジェクトを使用する場合に指定します。
* **logger** (`logging.Logger`): ログを出力するためのカスタムログオブジェクトを指定します。

### インスタンスメソッド

#### `get_current(self, remote_key: str) -> Dict[str, Any]`

現在の温湿度データを取得します。

* **remote\_key** (`str`): ```config.json```で設定したリモートセンサーのキー。```config.json```を使用していない場合や直接シリアル番号を入力したい場合はシリアル番号を入力する。

戻り値:

* 取得したデータを格納した辞書。

#### `get_data(self, remote_key: str, dt_from: Optional[str] = None, dt_to: Optional[str] = None, count: Optional[int] = None, hours: Optional[int] = None, as_df: bool = False, device_type: Optional[str] = None) -> Union[Dict[str, Any], pd.DataFrame]`

指定した期間・件数のデータを取得します。

* **remote_key** (`str`): ```config.json```で設定したリモートセンサーのキー。```config.json```を使用していない場合や直接シリアル番号を入力したい場合はシリアル番号を入力する。
* **dt_from** (`str` | `datetime` | `int`, オプション): 取得開始日時（ISO 8601形式、`datetime`型、またはUNIXタイムスタンプ）。
* **dt_to** (`str` | `datetime` | `int`, オプション): 取得終了日時。
* **count** (`int`, オプション): 取得件数（`device_type="default"` のみ有効）。
* **hours** (`int`, オプション): 過去何時間分を取得するか。`dt_from` と `dt_to` が指定されない場合に使用。
* **as_df** (`bool`, デフォルト: `False`): DataFrame形式でデータを取得するかどうか。(```True```の場合は```pandas```のインストールが必要)
* **device_type** (`str`, オプション): デバイスタイプを個別に上書きしたい場合に指定 (`"default"` または `"rtr500"`)。

戻り値:

* データが辞書形式で返されますが、`as_df=True` の場合、`pandas.DataFrame` 形式で返されます。

#### `get_latest_data(self, remote_key: str) -> Dict[str, Any]`

最新のデータを取得します。

* **remote\_key** (`str`): ```config.json```で設定したリモートセンサーのキー。```config.json```を使用していない場合や直接シリアル番号を入力したい場合はシリアル番号を入力する。

戻り値:

* 最新のデータを格納した辞書。

#### `get_alerts(self, remote_key: str) -> Dict[str, Any]`

アラートデータを取得します。

* **remote\_key** (`str`): ```config.json```で設定したリモートセンサーのキー。```config.json```を使用していない場合や直接シリアル番号を入力したい場合はシリアル番号を入力する。

戻り値:

* アラートデータを格納した辞書。

### ユーティリティ関数

#### `parse_current(json_current: Dict[str, Any]) -> Tuple[datetime, float, float]`

`get_current`のレスポンスから、時刻、温度、湿度を抽出します。

* **json\_current** (`Dict[str, Any]`): `get_current`のレスポンスのJSON。

戻り値:

* `datetime`型の時刻、`float`型の温度、`float`型の湿度。

#### `parse_data(json_data: Dict[str, Any]) -> Tuple[list, list, list]`

`get_data`または`get_latest_data`のレスポンスから、時刻、温度、湿度をリスト形式で抽出します。

* **json\_data** (`Dict[str, Any]`): `get_data`または`get_latest_data`のレスポンスのJSON。

戻り値:

* 時刻のリスト（`List[datetime]`）、温度のリスト（`List[float]`）、湿度のリスト（`List[float]`）。
