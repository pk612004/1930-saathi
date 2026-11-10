"""Phone-call path: simulated Twilio / Exotel media streams against the real server."""
import base64
import json
import os
import threading
import time

import numpy as np

from saathi import audio as A
from saathi import telephony as Tel
from saathi.providers.gnani import STTResult
from saathi.providers.llm import NoLLM
from saathi.providers.ws import OP_CLOSE, OP_TEXT, WebSocket
from saathi.server import App, serve
from saathi.store import Store


class ScriptSTT:
    name = "script-stt"

    def __init__(self, lines):
        self.lines = list(lines)
        self.heard_rates = []

    def transcribe(self, wav, language=None):
        x, sr = A.read_wav(wav)
        self.heard_rates.append(sr)
        return STTResult(text=self.lines.pop(0) if self.lines else "haan", provider=self.name, latency_ms=1.0)


class ToneTTS:
    name = "tone-tts"

    def synthesize(self, text, language="hi-IN", voice=None, speed=1.0):
        sr = 16000
        t = np.arange(int(0.3 * sr)) / sr
        return {"audio": A.write_wav(0.2 * np.sin(2 * np.pi * 300 * t), sr), "provider": self.name, "latency_ms": 1}


def test_mulaw_roundtrip():
    x = np.sin(np.linspace(0, 20 * np.pi, 8000)).astype(np.float32) * 0.5
    y = Tel.mulaw_decode(Tel.mulaw_encode(x))
    snr = 10 * np.log10(np.mean(x ** 2) / np.mean((x - y) ** 2))
    assert snr > 30  # G.711 gives ~38 dB on a sine


def test_vad_finds_one_utterance():
    sr = 8000
    rng = np.random.default_rng(0)
    quiet = 0.002 * rng.standard_normal(sr)
    speech = 0.3 * np.sin(2 * np.pi * 220 * np.arange(sr) / sr)
    v = Tel.EnergyVAD()
    events = []
    for chunk in np.split(np.concatenate([quiet, speech, quiet]).astype(np.float32), 150):
        events += v.feed(chunk)
    ends = [e for e in events if isinstance(e, tuple)]
    assert events[0] == "start" and len(ends) == 1
    # 300 ms pre-roll + 1 s speech + 700 ms end-of-speech silence
    assert 1.8 < len(ends[0][1]) / sr < 2.1


def test_twiml_has_stream_and_token():
    xml = Tel.twiml_response("saathi.example.in", {"From": ["+919999900001"], "CallSid": ["CA1"]})
    assert 'wss://saathi.example.in/twilio/stream' in xml and Tel.stream_token("CA1") in xml
    assert 'value="+919999900001"' in xml


def test_twilio_signature():
    params = {"CallSid": ["CA1"], "From": ["+91981"]}
    import hashlib, hmac
    data = "https://x/twilio/voice" + "CallSidCA1From+91981"
    sig = base64.b64encode(hmac.new(b"tok", data.encode(), hashlib.sha1).digest()).decode()
    assert Tel.twilio_signature_ok("https://x/twilio/voice", params, sig, "tok")
    assert not Tel.twilio_signature_ok("https://x/twilio/voice", params, sig, "other")


def _speech_then_silence(provider):
    sr = 8000
    rng = np.random.default_rng(1)
    sig = np.concatenate([0.002 * rng.standard_normal(sr // 2), 0.3 * np.sin(2 * np.pi * 220 * np.arange(sr) / sr),
                          0.002 * rng.standard_normal(sr)]).astype(np.float32)
    enc = Tel.mulaw_encode if provider == "twilio" else Tel.pcm16_encode
    step = 160
    return [enc(sig[i:i + step]) for i in range(0, len(sig), step)]


def _run_call(provider, port, sid_key, start_msg, path):
    ws = WebSocket(f"ws://127.0.0.1:{port}{path}", timeout=10).connect()
    ws.send_text(json.dumps({"event": "connected"}))
    ws.send_text(json.dumps(start_msg))
    got = {"media": 0, "mark": 0}
    ws.settimeout(5)

    def reader():
        try:
            while True:
                op, payload = ws.recv()
                if op == OP_CLOSE:
                    return
                m = json.loads(payload)
                if m.get("event") in got:
                    got[m["event"]] += 1
                    assert m.get(sid_key) == "SID1"
        except Exception:
            return
    th = threading.Thread(target=reader, daemon=True)
    th.start()
    time.sleep(0.3)
    greeting_media = got["media"]
    try:
        for frame in _speech_then_silence(provider):
            ws.send_text(json.dumps({"event": "media", sid_key: "SID1",
                                     "media": {"payload": base64.b64encode(frame).decode()}}))
    except OSError:          # server hung up (e.g. bad token)
        return greeting_media, got
    deadline = time.time() + 5
    while time.time() < deadline and got["mark"] < 2:
        time.sleep(0.05)
    ws.send_text(json.dumps({"event": "stop", sid_key: "SID1"}))
    time.sleep(0.2)
    ws.close()
    return greeting_media, got


def _app():
    stt = ScriptSTT(["UPI se 45 hazaar kat gaye bees minute pehle"])
    app = App(store=Store(), stt=stt, tts=ToneTTS(), llm=NoLLM(), require_login=False)
    httpd, _ = serve("127.0.0.1", 0, app)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return app, stt, httpd, httpd.server_address[1]


def test_twilio_call_end_to_end():
    app, stt, httpd, port = _app()
    try:
        start = {"event": "start", "streamSid": "SID1",
                 "start": {"streamSid": "SID1", "callSid": "CA9",
                           "mediaFormat": {"encoding": "audio/x-mulaw", "sampleRate": 8000, "channels": 1},
                           "customParameters": {"caller": "+919999900001", "callSid": "CA9",
                                                "token": Tel.stream_token("CA9")}}}
        greeting, got = _run_call("twilio", port, "streamSid", start, "/twilio/stream")
        assert greeting > 0                       # greeting audio played to the caller
        assert got["mark"] >= 2                   # greeting + one reply
        case = next(iter(app.store.cases.values()))
        assert case.channel == "twilio" and case.caller_number == "9999900001"
        assert case.caller_number_source == "caller_id"
        assert case.transactions[0].amount == 45000 and stt.heard_rates == [8000]
    finally:
        httpd.shutdown()


def test_twilio_bad_token_rejected():
    app, stt, httpd, port = _app()
    try:
        start = {"event": "start", "streamSid": "SID1",
                 "start": {"customParameters": {"caller": "+919999900001", "callSid": "CA9", "token": "forged"}}}
        greeting, got = _run_call("twilio", port, "streamSid", start, "/twilio/stream")
        assert not app.store.cases and greeting == 0
    finally:
        httpd.shutdown()


def test_exotel_call_end_to_end():
    os.environ["EXOTEL_STREAM_KEY"] = "k123"
    app, stt, httpd, port = _app()
    try:
        start = {"event": "start", "stream_sid": "SID1",
                 "start": {"stream_sid": "SID1", "from": "09999900001",
                           "media_format": {"encoding": "base64", "sample_rate": "8000"}}}
        greeting, got = _run_call("exotel", port, "stream_sid", start, "/exotel/stream?key=k123")
        case = next(iter(app.store.cases.values()))
        assert case.channel == "exotel" and case.caller_number == "9999900001"
        assert got["mark"] >= 2
    finally:
        httpd.shutdown()
