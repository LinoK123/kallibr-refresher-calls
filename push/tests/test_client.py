import pytest

from supabase_client import Client, PushError


class Resp:
    def __init__(self, status, body=None, headers=None):
        self.status_code, self._body, self.headers = status, body, headers or {}
        self.text = "" if body is None else str(body)
        self.content = b"" if body is None else b"x"

    def json(self):
        return self._body


class Session:
    def __init__(self, responses):
        self.headers, self.calls, self.responses = {}, [], list(responses)

    def request(self, method, url, **kw):
        self.calls.append((method, url, kw))
        return self.responses.pop(0)


def test_select_pages_through_every_row():
    s = Session([Resp(200, [{"id": i} for i in range(1000)]), Resp(200, [{"id": 1000}])])
    rows = Client("https://x.supabase.co/", "k", session=s, wait=0).select("lines", "id", status="eq.won")
    assert len(rows) == 1001
    assert [c[2]["params"]["offset"] for c in s.calls] == [0, 1000]
    assert s.calls[0][1] == "https://x.supabase.co/rest/v1/lines" and s.calls[0][2]["params"]["status"] == "eq.won"
    assert s.headers["apikey"] == "k" and s.headers["Authorization"] == "Bearer k"


def test_read_retries_5xx_then_succeeds():
    s = Session([Resp(503, "busy"), Resp(200, [])])
    assert Client("https://x", "k", session=s, wait=0).select("lines", "id") == []
    assert len(s.calls) == 2


def test_write_failure_raises_without_retry():
    s = Session([Resp(500, "boom")])
    with pytest.raises(PushError, match="500"):
        Client("https://x", "k", session=s, wait=0).insert("stage_lines", [{"a": 1}])
    assert len(s.calls) == 1


def test_insert_returning_and_rpc():
    s = Session([Resp(201, [{"id": 5}]), Resp(200, {"wins": 2})])
    c = Client("https://x", "k", session=s, wait=0)
    assert c.insert("sync_runs", [{"result": "running"}], returning=True) == [{"id": 5}]
    assert s.calls[0][2]["headers"]["Prefer"] == "return=representation"
    assert c.rpc("apply_push", p_run_id=5) == {"wins": 2}
    assert s.calls[1][1].endswith("/rest/v1/rpc/apply_push") and s.calls[1][2]["json"] == {"p_run_id": 5}


def test_error_message_never_contains_the_key():
    s = Session([Resp(401, "Invalid API key")])
    with pytest.raises(PushError) as e:
        Client("https://x", "super-secret", session=s, wait=0).update("sync_runs", {"result": "failed"}, id="eq.1")
    assert "super-secret" not in str(e.value)
