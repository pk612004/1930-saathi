import base64
import http.client
import json
import threading

import pytest

from saathi.providers.gnani import MockSTT, MockTTS, PrismaSTT, TimbreTTS
from saathi.providers.llm import NoLLM
from saathi.server import App, serve
from saathi.store import Store

from . import fake_gnani as F


def start_app(app):
    httpd, _ = serve("127.0.0.1", 0, app)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


COOKIE = {}


def req(port, method, path, body=None, cookie=True, ctype="application/json"):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": ctype}
    if cookie and COOKIE.get(port):
        headers["Cookie"] = COOKIE[port]
    conn.request(method, path, body=data, headers=headers)
    r = conn.getresponse()
    raw = r.read()
    sc = r.getheader("Set-Cookie")
    if sc and "saathi_session=" in sc and "Max-Age=0" not in sc:
        COOKIE[port] = sc.split(";")[0]
    try:
        return r.status, json.loads(raw)
    except ValueError:
        return r.status, raw


@pytest.fixture()
def mock_server():
    app = App(store=Store(), stt=MockSTT(), tts=MockTTS(), llm=NoLLM())
    httpd, port = start_app(app)
    st, _ = req(port, "POST", "/api/login", {"username": "admin", "password": app.first_password})
    assert st == 200
    yield port
    httpd.shutdown()


def test_full_call_and_console(mock_server):
    port = mock_server
    st, h = req(port, "GET", "/api/health")
    assert st == 200 and h["mock"] is True
    st, call = req(port, "POST", "/api/calls", {})
    cid = call["call_id"]
    for line in ["UPI se 45 hazaar kat gaye bees minute pehle", "4 1 2 3 5 6 7 8 9 0 1 2", "haan",
                 "ramesh at the rate ybl", "haan", "SBI", "nahi", "haan"]:
        st, r = req(port, "POST", f"/api/calls/{cid}/turn", {"text": line})
        assert st == 200
    assert r["done"] is True
    st, q = req(port, "GET", "/api/queue")
    assert q["queue"][0]["id"] == cid
    st, d = req(port, "GET", f"/api/cases/{cid}")
    assert d["drafts"]["ncrp"]["transactions"][0]["reference_utr"] == "412356789012"
    st, d = req(port, "POST", f"/api/cases/{cid}/action", {"action": "freeze_requested"})
    assert d["status"] == "freeze_requested"


def test_seed_is_idempotent(mock_server):
    port = mock_server
    req(port, "POST", "/api/demo/seed", {})
    req(port, "POST", "/api/demo/seed", {})
    st, cl = req(port, "GET", "/api/clusters")
    rings = [c for c in cl["clusters"] if c["is_ring"]]
    assert len(rings) == 1 and rings[0]["size"] == 3


def test_audio_in_mock_mode_explains_itself(mock_server):
    port = mock_server
    st, call = req(port, "POST", "/api/calls", {})
    wav = base64.b64encode(F.tiny_wav()).decode()
    st, r = req(port, "POST", f"/api/calls/{call['call_id']}/turn", {"audio_b64": wav})
    assert st == 200 and r["reply"] is None and "Mock mode" in r["stt_error"]


def test_static_and_traversal(mock_server):
    port = mock_server
    for p in ("/", "/caller.html", "/console.html", "/js/caller.js", "/css/app.css"):
        assert req(port, "GET", p)[0] == 200
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("GET", "/../saathi/config.py")
    assert conn.getresponse().status in (403, 404)


def test_live_providers_through_server():
    http_srv, ws_srv = F.start()
    base = f"http://127.0.0.1:{http_srv.server_address[1]}"
    app = App(store=Store(), stt=PrismaSTT(api_key=F.API_KEY, base_url=base),
              tts=TimbreTTS(api_key=F.API_KEY, base_url=base, cache_dir=None), llm=NoLLM(), require_login=False)
    import tempfile
    from pathlib import Path
    app.tts.cache_dir = Path(tempfile.mkdtemp())
    httpd, port = start_app(app)
    try:
        st, call = req(port, "POST", "/api/calls", {})
        assert call["audio_b64"] and call["tts_provider"] == "gnani-timbre"
        wav = base64.b64encode(F.tiny_wav(1.0, 8000)).decode()
        st, r = req(port, "POST", f"/api/calls/{call['call_id']}/turn", {"audio_b64": wav})
        assert r["heard"] == F.TRANSCRIPT and r["stt_provider"] == "gnani-prisma"
        assert r["case"]["transactions"][0]["amount"] == 45000
    finally:
        httpd.shutdown()
        http_srv.shutdown()
        ws_srv.shutdown()


def test_console_api_requires_login():
    app = App(store=Store(), stt=MockSTT(), tts=MockTTS(), llm=NoLLM())
    httpd, port = start_app(app)
    try:
        assert req(port, "GET", "/api/queue", cookie=False)[0] == 401
        assert req(port, "POST", "/api/demo/seed", {}, cookie=False)[0] == 401
        assert req(port, "POST", "/api/login", {"username": "admin", "password": "wrong-password"}, cookie=False)[0] == 401
        # caller side stays public
        assert req(port, "POST", "/api/calls", {}, cookie=False)[0] == 200
        # form posts (CSRF shape) are refused
        assert req(port, "POST", "/api/calls", {}, cookie=False, ctype="application/x-www-form-urlencoded")[0] == 415
    finally:
        httpd.shutdown()


def test_login_rate_limited():
    app = App(store=Store(), stt=MockSTT(), tts=MockTTS(), llm=NoLLM(), rate_limits={"login": 3})
    httpd, port = start_app(app)
    try:
        codes = [req(port, "POST", "/api/login", {"username": "x", "password": "y"}, cookie=False)[0] for _ in range(5)]
        assert codes[:3] == [401, 401, 401] and 429 in codes[3:]
    finally:
        httpd.shutdown()


def test_otp_verification_and_audit(mock_server):
    port = mock_server
    st, call = req(port, "POST", "/api/calls", {"caller_number": "99999 00001"})
    cid = call["call_id"]
    for line in ["UPI se 45 hazaar kat gaye bees minute pehle", "pata nahi", "ramesh at the rate ybl", "haan",
                 "SBI", "nahi", "haan"]:
        st, r = req(port, "POST", f"/api/calls/{cid}/turn", {"text": line})
    assert r["done"]
    st, ob = req(port, "GET", "/api/outbox")
    sms = ob["outbox"][0]
    assert sms["to_number"] == "9999900001" and cid in sms["body"]
    code = sms["body"].rsplit(" ", 1)[-1]
    assert req(port, "POST", "/api/verify", {"case_id": cid, "code": "000000" if code != "000000" else "111111"})[1]["ok"] is False
    assert req(port, "POST", "/api/verify", {"case_id": cid, "code": code})[1]["ok"] is True
    st, d = req(port, "GET", f"/api/cases/{cid}")
    assert d["verification"] == "otp_verified"
    actions = [a["action"] for a in d["audit"]]
    assert "case_filed" in actions and "otp_verify_fail" in actions and "otp_verify_ok" in actions


def test_persistence_across_restart(tmp_path):
    db = str(tmp_path / "s.db")
    s1 = Store(db)
    d = s1.new_call()
    d.greeting()
    d.step("45 hazaar gaye")
    s1.save(d.case)
    s2 = Store(db)
    assert s2.cases[d.case.id].transactions[0].amount == 45000


def test_collect_requires_key_and_consent(tmp_path, monkeypatch):
    from saathi.config import settings
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setenv("COLLECT_KEY", "k1")
    app = App(store=Store(), stt=MockSTT(), tts=MockTTS(), llm=NoLLM(), require_login=False)
    httpd, port = start_app(app)
    try:
        wav = base64.b64encode(F.tiny_wav(0.5)).decode()
        body = {"key": "bad", "consent": True, "field": "utr", "expected": "412356789012", "lang": "hi", "audio_b64": wav}
        assert req(port, "POST", "/api/collect", body, cookie=False)[0] == 403
        body["key"] = "k1"
        body["consent"] = False
        assert req(port, "POST", "/api/collect", body, cookie=False)[0] == 400
        body["consent"] = True
        st, r = req(port, "POST", "/api/collect", body, cookie=False)
        assert st == 200 and (tmp_path / "recordings" / f"{r['id']}.wav").exists()
        assert "412356789012" in (tmp_path / "recordings" / "manifest.jsonl").read_text()
    finally:
        httpd.shutdown()
