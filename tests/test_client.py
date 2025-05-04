# tests/test_client.py
import json
import pytest
from datetime import datetime
import pandas as pd
from requests.exceptions import HTTPError

from ondotori_client.client import OndotoriClient, parse_current, parse_data


class DummyResponse:
    def __init__(self, data, status=200):
        self._data = data
        self.status_code = status
        # raise_for_status で使われる
        self.reason = ""
        self.url = ""

    def raise_for_status(self):
        if not (200 <= self.status_code < 300):
            raise HTTPError(f"{self.status_code} Error")

    def json(self):
        return self._data


@pytest.fixture
def cfg_dict():
    return {
        "api_key": "KEY123",
        "login_id": "ID123",
        "login_pass": "PASS123",
        "default_rtr500_base": "BaseA",
        "bases": {
            "BaseA": {"serial": "BASE_SER_A"},
        },
        "remote_map": {
            "R1": {"serial": "REM_SER_1", "type": "rtr500", "base": "BaseA"},
            "D1": {"serial": "REM_SER_2", "type": "default"},
        },
    }


@pytest.fixture
def client_default(cfg_dict):
    # config dict から default モードで初期化
    return OndotoriClient(config=cfg_dict, device_type="default", verbose=True)


@pytest.fixture
def client_rtr(cfg_dict):
    # config dict から rtr500 モードで初期化
    return OndotoriClient(config=cfg_dict, device_type="rtr500", verbose=True)


def test_parse_current_and_data_helpers():
    j = {
        "devices": [
            {"unixtime": "1600000000", "channel": [{"value": "2.2"}, {"value": "3.3"}]}
        ]
    }
    ts, t, h = parse_current(j)
    assert isinstance(ts, datetime)
    assert t == 2.2
    assert h == 3.3

    jd = {"data": [{"unixtime": "1600000000", "ch1": "4.4", "ch2": "5.5"}]}
    times, temps, hums = parse_data(jd)
    assert len(times) == 1 and isinstance(times[0], datetime)
    assert temps == [4.4]
    assert hums == [5.5]


def test_init_with_config_file(tmp_path, cfg_dict):
    # JSON ファイル経由でも初期化できる
    p = tmp_path / "cfg.json"
    p.write_text(json.dumps(cfg_dict), encoding="utf-8")
    cli = OndotoriClient(config=str(p), device_type="rtr500")
    # 内部 auth が読み込まれていることを確認
    assert cli._auth["api-key"] == cfg_dict["api_key"]


def test_direct_args_init_and_missing():
    # 直接引数だけでも動く
    cli = OndotoriClient(
        api_key="A",
        login_id="L",
        login_pass="P",
        base_serial="B",
        device_type="default",
    )
    assert cli._auth["api-key"] == "A"
    # config も args も与えないと例外
    with pytest.raises(ValueError):
        OndotoriClient()


def test_get_current_default(monkeypatch, client_default):
    dummy = {"devices": [{"unixtime": "1", "channel": []}]}

    def fake_post(url, headers=None, json=None, timeout=None):
        assert url == client_default._URL_CURRENT
        # D1 の serial は cfg.remote_map["D1"]["serial"]
        assert json["remote-serial"] == ["REM_SER_2"]
        return DummyResponse(dummy)

    monkeypatch.setattr(client_default.session, "post", fake_post)
    res = client_default.get_current("D1")
    assert res == dummy


def test_get_current_direct_key(monkeypatch):
    # 直接 args モード
    cli = OndotoriClient(
        api_key="X",
        login_id="Y",
        login_pass="Z",
        base_serial="BASE0",
        device_type="default",
    )
    dummy = {"devices": [{"unixtime": "2", "channel": []}]}

    def fake_post(url, headers=None, json=None, timeout=None):
        assert json["remote-serial"] == ["CUSTOM"]
        return DummyResponse(dummy)

    monkeypatch.setattr(cli.session, "post", fake_post)
    assert cli.get_current("CUSTOM") == dummy


def test_get_data_default(monkeypatch, client_default):
    dummy = {"data": [{"unixtime": "10", "ch1": "7.7", "ch2": "8.8"}]}

    def fake_post(url, headers=None, json=None, timeout=None):
        assert url == client_default._URL_DATA_DEFAULT
        # count がペイロードに乗る
        assert json["number"] == 5
        return DummyResponse(dummy)

    monkeypatch.setattr(client_default.session, "post", fake_post)
    res = client_default.get_data("D1", dt_from=0, dt_to=10, count=5)
    assert res == dummy


def test_get_data_rtr500_and_as_df(monkeypatch, client_rtr):
    dummy = {"data": [{"unixtime": "20", "ch1": "1.1", "ch2": "2.2"}]}

    def fake_post(url, headers=None, json=None, timeout=None):
        assert url == client_rtr._URL_DATA_RTR500
        # base-serial も入っている
        assert json["base-serial"] == "BASE_SER_A"
        return DummyResponse(dummy)

    monkeypatch.setattr(client_rtr.session, "post", fake_post)
    df = client_rtr.get_data("R1", hours=1, as_df=True)
    # DataFrame になっていること
    assert isinstance(df, pd.DataFrame)
    assert df["temp_C"].iloc[0] == 1.1
    assert df["hum_%"].iloc[0] == 2.2


def test_get_latest_data(monkeypatch, client_default, client_rtr):
    dummy = {"data": []}

    # default
    def fake_def(url, headers=None, json=None, timeout=None):
        assert url == client_default._URL_LATEST_DEFAULT
        return DummyResponse(dummy)

    monkeypatch.setattr(client_default.session, "post", fake_def)
    assert client_default.get_latest_data("D1") == dummy

    # rtr500
    def fake_rtr(url, headers=None, json=None, timeout=None):
        assert url == client_rtr._URL_LATEST_RTR500
        assert json["base-serial"] == "BASE_SER_A"
        return DummyResponse(dummy)

    monkeypatch.setattr(client_rtr.session, "post", fake_rtr)
    assert client_rtr.get_latest_data("R1") == dummy


def test_get_alerts(monkeypatch, client_default, client_rtr):
    dummy = {"alerts": []}

    # default
    def fake_def(url, headers=None, json=None, timeout=None):
        assert url == client_default._URL_ALERT
        return DummyResponse(dummy)

    monkeypatch.setattr(client_default.session, "post", fake_def)
    assert client_default.get_alerts("D1") == dummy

    # rtr500
    def fake_rtr(url, headers=None, json=None, timeout=None):
        assert url == client_rtr._URL_ALERT
        assert json["base-serial"] == "BASE_SER_A"
        return DummyResponse(dummy)

    monkeypatch.setattr(client_rtr.session, "post", fake_rtr)
    assert client_rtr.get_alerts("R1") == dummy
