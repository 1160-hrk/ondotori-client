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

#### `get_data(self, remote_key: str, dt_from: Optional[str] = None, dt_to: Optional[str] = None, hours: Optional[int] = None, as_df: bool = False) -> Union[Dict[str, Any], pd.DataFrame]`

指定した期間のデータを取得します。

* **remote\_serial** (`str`): ```config.json```で設定したリモートセンサーのキー。```config.json```を使用していない場合や直接シリアル番号を入力したい場合はシリアル番号を入力する。
* **dt\_from** (`str`, オプション): 取得開始日時（ISO 8601形式、```datetime```型オブジェクト、またはint型のUNIXタイムスタンプ）。指定しない場合、`hours`引数を使用します。
* **dt\_to** (`str`, オプション): 取得終了日時（ISO 8601形式、```datetime```型オブジェクト、またはint型のUNIXタイムスタンプ）。指定しない場合、現在時刻が使用されます。
* **hours** (`int`, オプション): 取得する過去の時間数。`dt_from`と`dt_to`が指定されない場合、この値が使用されます。
* **as\_df** (`bool`, デフォルト: `False`): DataFrame形式でデータを取得するかどうか。（```True```の場合は```pandas```をインストールしている必要があります。）

戻り値:

* データが辞書形式で返されますが、`as_df=True`の場合、`pandas.DataFrame`形式で返されます。

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
