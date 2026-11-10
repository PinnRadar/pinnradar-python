import io
import json
import urllib.error
import urllib.request

import pytest

import pinnradar
from pinnradar import AuthError, Client, RateLimitError, no_vig, parse_sse


class FakeResp(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def capture(monkeypatch, body=b"{}", error=None):
    seen = {}

    def fake(req, timeout=None):
        seen["url"] = req.full_url
        seen["headers"] = {k.lower(): v for k, v in req.header_items()}
        if error:
            raise error
        return FakeResp(body)

    monkeypatch.setattr(urllib.request, "urlopen", fake)
    return seen


def test_requires_key(monkeypatch):
    monkeypatch.delenv("PINNRADAR_API_KEY", raising=False)
    monkeypatch.delenv("PINNRADAR_KEY", raising=False)
    with pytest.raises(AuthError):
        Client()


def test_env_key(monkeypatch):
    monkeypatch.setenv("PINNRADAR_API_KEY", "abc")
    assert Client().api_key == "abc"


def test_markets_url_and_header(monkeypatch):
    seen = capture(monkeypatch, b'{"sport_id":1,"events":[]}')
    out = Client("k").markets(1, include_specials=True)
    assert out["sport_id"] == 1
    assert seen["url"] == "https://pinnradar.com/kit/v1/markets?sport_id=1&event_type=live&include_specials=1"
    assert seen["headers"]["x-api-key"] == "k"
    assert seen["headers"]["user-agent"].startswith("pinnradar-python/")


def test_drops_csv_and_unwrap(monkeypatch):
    seen = capture(monkeypatch, json.dumps({"drops": [{"from": 2.0, "to": 1.8}]}).encode())
    rows = Client("k").drops(mode="prematch", markets=["total", "spread"], periods=[0, 1], min_drop_pct=3)
    assert rows == [{"from": 2.0, "to": 1.8}]
    assert "markets=total%2Cspread" in seen["url"] and "periods=0%2C1" in seen["url"] and "min_drop_pct=3" in seen["url"]


def http_error(code, body=b"{}", headers=None):
    import email.message

    msg = email.message.Message()
    for k, v in (headers or {}).items():
        msg[k] = v
    return urllib.error.HTTPError("https://pinnradar.com/x", code, "err", msg, io.BytesIO(body))


def test_rate_limit(monkeypatch):
    capture(monkeypatch, error=http_error(429, b'{"error":"rate_limited"}', {"Retry-After": "2"}))
    with pytest.raises(RateLimitError) as e:
        Client("k").markets(1)
    assert e.value.retry_after == 2.0


def test_auth_error(monkeypatch):
    capture(monkeypatch, error=http_error(401, b'{"error":"invalid_key"}'))
    with pytest.raises(AuthError) as e:
        Client("k").details(5)
    assert "invalid_key" in str(e.value)


def test_parse_sse():
    lines = [": keepalive\n", "data: [1,2]\n", "\n", "event: x\n", "data: {\"a\":\n", "data: 1}\n", "\n"]
    assert list(parse_sse(lines)) == ["[1,2]", '{"a":\n1}']


def test_stream_drops(monkeypatch):
    body = b'data: [{"from":2.0,"to":1.8},{"from":3.0,"to":2.5}]\n\n: ping\n\ndata: {"from":1.9,"to":1.7}\n\n'
    capture(monkeypatch, body)
    got = list(Client("k").stream_drops(min_drop=3, reconnect=False))
    assert [d["to"] for d in got] == [1.8, 2.5, 1.7]


def test_no_vig():
    assert [round(x, 3) for x in no_vig([1.952, 1.952])] == [2.0, 2.0]
    fair = no_vig([2.1, 3.45, 3.7], method="power")
    assert abs(sum(1 / x for x in fair) - 1) < 1e-9


def test_version():
    assert pinnradar.__version__
