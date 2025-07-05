# インストールガイド

本ライブラリ **ondotori-client** は PyPI に公開されています。以下のコマンドを実行することで、Python 環境にインストールできます。

## 1. 通常インストール
```bash
pip install ondotori-client
```

## 2. DataFrame 出力（pandas 連携）を使用したい場合
```bash
pip install "ondotori-client[dataframe]"
```
これにより、`get_data(..., as_df=True)` で `pandas.DataFrame` を直接受け取れるようになります。

## 3. 開発版をインストール（リポジトリをクローンして利用）
```bash
# 1. リポジトリを取得
git clone https://github.com/1160-hrk/ondotori-client.git
cd ondotori-client

# 2. 開発モードでインストール
pip install -e ".[dataframe]"
```

## 4. サポート環境
* Python 3.8 以上
* OS: Linux, macOS, Windows（WSL 含む）

> 注: Internet への HTTPS アクセスが必要です。企業ネットワーク内などでプロキシを使用する場合は、`requests.Session` に `proxies` を設定してください。

## 5. アンインストール
```bash
pip uninstall ondotori-client
```

---

インストール手順はこれで完了です。次は [`docs/usage.md`](usage.md) を参照して、実際の使用方法を確認してみましょう。
