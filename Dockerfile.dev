# ───────────── dev stage ─────────────
FROM python:3.12-slim

WORKDIR /work

# ビルドツール + Python ヘッダー + git など
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      build-essential python3-dev git \
 && rm -rf /var/lib/apt/lists/*

# メタデータ＋コードコピー（キャッシュ用）
COPY pyproject.toml ./
COPY src/           ./src/

# 依存ファイルコピー
COPY requirements.txt requirements-dev.txt ./

# まず本番依存
RUN pip install --no-cache-dir -r requirements.txt

# 次に開発モードでインストール（pyproject.toml/setup.cfg の dependencies も自動で取れるならこのあとでOK）
RUN pip install --no-cache-dir -e .

# 最後に開発用依存
RUN pip install --no-cache-dir -r requirements-dev.txt

# サンプルもコピー
COPY examples/ ./examples/

# 起動維持
ENTRYPOINT ["tail", "-f", "/dev/null"]
