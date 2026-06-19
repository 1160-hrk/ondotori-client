from __future__ import annotations

import os
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from ondotori_client import ClientConfig, OndotoriClient

pytestmark = pytest.mark.integration

_CONFIG_PATH = Path("configs/config.json")
_RUN_REAL_API = os.getenv("ONDOTORI_RUN_INTEGRATION") == "1"


def _remote_key(config: ClientConfig) -> str:
    specified = os.getenv("ONDOTORI_REMOTE_KEY")
    if specified:
        return specified
    if config.remotes:
        return next(iter(config.remotes))
    pytest.skip(
        "remote_map が空です．ONDOTORI_REMOTE_KEY にシリアル番号を指定してください"
    )


@pytest.mark.skipif(
    not _RUN_REAL_API,
    reason="実 API テストは ONDOTORI_RUN_INTEGRATION=1 のときだけ実行します",
)
def test_real_current_and_recent_data() -> None:
    if not _CONFIG_PATH.exists():
        pytest.skip("configs/config.json がありません")

    config = ClientConfig.from_file(_CONFIG_PATH)
    remote_key = _remote_key(config)

    with OndotoriClient(
        config,
        timeout=(5.0, 20.0),
        default_timezone=ZoneInfo("Asia/Tokyo"),
    ) as client:
        current = client.get_current(remote_key)
        recent = client.get_data(remote_key, hours=1)

    assert "devices" in current
    assert "data" in recent
