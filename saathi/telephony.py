"""Real phone calls: Twilio Media Streams and Exotel Voicebot (bidirectional WebSocket audio).

Call flow
  1. Caller dials your Twilio / Exotel number.
  2. Twilio: the number's voice webhook is POST https://<host>/twilio/voice, which returns TwiML
     <Connect><Stream url="wss://<host>/twilio/stream"> ...
     Exotel: add a "Voicebot" applet in the call flow pointing to wss://<host>/exotel/stream?key=<EXOTEL_STREAM_KEY>
  3. Audio arrives as 8 kHz frames (Twilio: mu-law, Exotel: 16-bit PCM), base64 in JSON messages.
  4. An energy VAD finds where the caller stops talking -> Prisma -> Saathi engine -> Timbre.
  5. The reply is sent back on the same socket. If the caller talks over it (barge-in), playback
     is cleared and Saathi listens.

The caller's number comes from caller ID, so the complaint is tied to the phone that called
(`caller_number_source = caller_id`), and the SMS/OTP goes to that number.

Twilio's message format is documented in its Media Streams docs. Exotel's Voicebot format is
implemented from its public description and should be checked against your Exotel account
before go-live.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import struct
import threading
import time
from html import escape
from typing import Dict, List, Optional
from urllib.parse import parse_qs, urlparse

import numpy as np

from . import audio as A
from .providers.ws import OP_BINARY, OP_CLOSE, OP_PING, OP_PONG, OP_TEXT, decode_frame, encode_frame

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
STREAM_SECRET = os.environ.get("TELEPHONY_SECRET") or secrets.token_hex(16)

# ---------------------------------------------------------------- G.711 mu-law


def mulaw_decode(data: bytes) -> np.ndarray:
    u = ~np.frombuffer(data, dtype=np.uint8)
    sign = u & 0x80
    exponent = (u >> 4) & 0x07
    mantissa = u & 0x0F
    sample = ((mantissa.astype(np.int32) << 3) + 0x84) << exponent
    sample = sample - 0x84
    sample = np.where(sign != 0, -sample, sample)
    return (sample / 32768.0).astype(np.float32)


def mulaw_encode(x: np.ndarray) -> bytes:
    BIAS, CLIP = 0x84, 32635
    s = np.clip((np.asarray(x, dtype=np.float32) * 32768.0), -32768, 32767).astype(np.int32)
    sign = (s < 0).astype(np.int32) << 7
    s = np.minimum(np.abs(s), CLIP) + BIAS
    exponent = np.floor(np.log2(np.maximum(s, 1))).astype(np.int32) - 7
    exponent = np.clip(exponent, 0, 7)
    mantissa = (s >> (exponent + 3)) & 0x0F
    return (~(sign | (exponent << 4) | mantissa) & 0xFF).astype(np.uint8).tobytes()


def pcm16_decode(data: bytes) -> np.ndarray:
    return (np.frombuffer(data, dtype="<i2").astype(np.float32) / 32768.0)


def pcm16_encode(x: np.ndarray) -> bytes:
    return (np.clip(x, -1, 1) * 32767).astype("<i2").tobytes()


# ---------------------------------------------------------------- VAD


class EnergyVAD:
    """Adaptive energy voice-activity detector for 8 kHz, 20 ms frames.

    speech  = frame energy > noise floor + 9 dB (and above an absolute minimum)
    start   = 3 speech frames in a row (60 ms); 300 ms of pre-roll is kept
    end     = 700 ms of non-speech, or 15 s maximum utterance
    """

    def __init__(self, sr: int = 8000, frame_ms: int = 20, end_silence_ms: int = 700,
                 max_utt_s: float = 15.0, min_utt_s: float = 0.35):
        self.sr = sr
        self.frame = sr * frame_ms // 1000
        self.end_frames = end_silence_ms // frame_ms
        self.max_frames = int(max_utt_s * 1000 / frame_ms)
        self.min_frames = int(min_utt_s * 1000 / frame_ms)
        self.pre_roll: List[np.ndarray] = []
        self.pre_max = 300 // frame_ms
        self.noise_db = -55.0
        self.speaking = False
        self.run = 0
        self.silence = 0
        self.buf: List[np.ndarray] = []
        self._pending = np.zeros(0, dtype=np.float32)

    @staticmethod
    def db(frame: np.ndarray) -> float:
        return 10 * np.log10(float(np.mean(frame ** 2)) + 1e-10)

    def feed(self, samples: np.ndarray) -> List:
        """Returns a list of events: "start" and/or ("end", np.ndarray)."""
        events = []
        self._pending = np.concatenate([self._pending, samples])
        while len(self._pending) >= self.frame:
            f, self._pending = self._pending[:self.frame], self._pending[self.frame:]
            level = self.db(f)
            is_speech = level > max(self.noise_db + 9.0, -48.0)
            if not self.speaking:
                # track the noise floor only while nobody is talking
                self.noise_db = 0.95 * self.noise_db + 0.05 * level if level < self.noise_db + 9 else self.noise_db
                self.pre_roll.append(f)
                self.pre_roll = self.pre_roll[-self.pre_max:]
                self.run = self.run + 1 if is_speech else 0
                if self.run >= 3:
                    self.speaking = True
                    self.buf = list(self.pre_roll)
                    self.silence = 0
                    events.append("start")
            else:
                self.buf.append(f)
                self.silence = 0 if is_speech else self.silence + 1
                if self.silence >= self.end_frames or len(self.buf) >= self.max_frames:
                    utt = np.concatenate(self.buf)
                    self.speaking = False
                    self.run = 0
                    self.buf = []
                    self.pre_roll = []
                    if len(utt) >= self.min_frames * self.frame:
                        events.append(("end", utt))
        return events


# ---------------------------------------------------------------- Twilio webhook


def stream_token(call_sid: str) -> str:
    return hmac.new(STREAM_SECRET.encode(), call_sid.encode(), hashlib.sha256).hexdigest()[:32]


def twilio_signature_ok(url: str, params: Dict[str, List[str]], signature: str, auth_token: str) -> bool:
    data = url + "".join(k + params[k][0] for k in sorted(params))
    expected = base64.b64encode(hmac.new(auth_token.encode(), data.encode(), hashlib.sha1).digest()).decode()
    return hmac.compare_digest(expected, signature or "")


def twiml_response(host: str, form: Dict[str, List[str]]) -> str:
    caller = (form.get("From") or [""])[0]
    call_sid = (form.get("CallSid") or ["unknown"])[0]
    url = f"wss://{escape(host)}/twilio/stream"
    return ('<?xml version="1.0" encoding="UTF-8"?><Response><Connect>'
            f'<Stream url="{url}">'
            f'<Parameter name="caller" value="{escape(caller)}"/>'
            f'<Parameter name="callSid" value="{escape(call_sid)}"/>'
            f'<Parameter name="token" value="{stream_token(call_sid)}"/>'
            '</Stream></Connect></Response>')


# ---------------------------------------------------------------- WebSocket session


class MediaSession:
    def __init__(self, handler, app, provider: str):
        self.h = handler
        self.app = app
        self.provider = provider              # twilio | exotel
        self.sock = handler.connection
        self.send_lock = threading.Lock()
        self.stream_sid: Optional[str] = None
        self.call_id: Optional[str] = None
        self.vad = EnergyVAD()
        self.play_until = 0.0
        self.busy = False
        self.closed = False
        self.marks = 0
        self.log: List[str] = []

    # ---- frames
    def read_exact(self, n: int) -> bytes:
        data = self.h.rfile.read(n)
        if len(data) < n:
            raise ConnectionError("socket closed")
        return data

    def send_json(self, obj: Dict):
        with self.send_lock:
            if not self.closed:
                self.sock.sendall(encode_frame(OP_TEXT, json.dumps(obj).encode(), mask=False))

    # ---- audio out
    def _sid_key(self) -> str:
        return "streamSid" if self.provider == "twilio" else "stream_sid"

    def play_wav(self, wav: Optional[bytes]):
        if not wav or self.closed:
            return
        x, sr = A.read_wav(wav)
        y = A.resample(x, sr, 8000)
        payload_bytes = mulaw_encode(y) if self.provider == "twilio" else pcm16_encode(y)
        bytes_per_20ms = 160 if self.provider == "twilio" else 320
        for i in range(0, len(payload_bytes), bytes_per_20ms * 10):   # 200 ms per message
            chunk = payload_bytes[i:i + bytes_per_20ms * 10]
            self.send_json({"event": "media", self._sid_key(): self.stream_sid,
                            "media": {"payload": base64.b64encode(chunk).decode()}})
        self.marks += 1
        self.send_json({"event": "mark", self._sid_key(): self.stream_sid, "mark": {"name": f"reply-{self.marks}"}})
        self.play_until = time.monotonic() + len(y) / 8000.0

    def barge_in(self):
        if time.monotonic() < self.play_until:
            self.send_json({"event": "clear", self._sid_key(): self.stream_sid})
            self.play_until = 0.0
            self.log.append("barge-in")

    # ---- dialog
    def start(self, msg: Dict):
        if self.provider == "twilio":
            st = msg.get("start", {})
            self.stream_sid = msg.get("streamSid") or st.get("streamSid")
            params = st.get("customParameters", {}) or {}
            caller = params.get("caller")
            call_sid = params.get("callSid") or st.get("callSid", "")
            token = params.get("token")
            if os.environ.get("TELEPHONY_REQUIRE_TOKEN", "1") == "1" and token != stream_token(call_sid):
                self.log.append("bad stream token")
                raise PermissionError("stream token mismatch")
        else:
            st = msg.get("start", {})
            self.stream_sid = msg.get("stream_sid") or st.get("stream_sid")
            caller = st.get("from")
        res = self.app.start_call({"caller_number": caller, "caller_number_source": "caller_id",
                                   "caller_label": f"Phone caller ({self.provider})"}, channel=self.provider)
        self.call_id = res["call_id"]
        self.app.db.audit("telephony", "call_connected", self.call_id, self.provider)
        self.play_wav(base64.b64decode(res["audio_b64"]) if res.get("audio_b64") else None)

    def on_utterance(self, samples: np.ndarray):
        if not self.call_id or self.busy:
            return
        self.busy = True

        def work():
            try:
                wav = A.write_wav(samples, 8000)
                res = self.app.turn(self.call_id, {"audio_b64": base64.b64encode(wav).decode()}, with_voice=False)
                reply = res.get("reply")
                if reply:
                    voice = self.app.speak(reply, self.app.store.get_call(self.call_id).lang)
                    self.play_wav(base64.b64decode(voice["audio_b64"]) if voice.get("audio_b64") else None)
                    self.log.append(f"turn:{res.get('state')}")
            except Exception as e:  # keep the call alive on provider errors
                self.log.append(f"error:{e}")
            finally:
                self.busy = False
        threading.Thread(target=work, daemon=True).start()

    def on_media(self, msg: Dict):
        payload = base64.b64decode(msg.get("media", {}).get("payload", ""))
        if not payload:
            return
        x = mulaw_decode(payload) if self.provider == "twilio" else pcm16_decode(payload)
        for ev in self.vad.feed(x):
            if ev == "start":
                self.barge_in()
            elif isinstance(ev, tuple) and ev[0] == "end":
                self.on_utterance(ev[1])

    def run(self):
        while not self.closed:
            try:
                fin, op, payload = decode_frame(self.read_exact)
            except (ConnectionError, OSError, struct.error, ValueError):
                break
            if op == OP_CLOSE:
                break
            if op == OP_PING:
                with self.send_lock:
                    self.sock.sendall(encode_frame(OP_PONG, payload, mask=False))
                continue
            if op not in (OP_TEXT, OP_BINARY):
                continue
            try:
                msg = json.loads(payload.decode("utf-8"))
            except ValueError:
                continue
            ev = msg.get("event")
            if ev == "start":
                try:
                    self.start(msg)
                except PermissionError:
                    break
            elif ev == "media":
                self.on_media(msg)
            elif ev == "stop":
                break
        self.closed = True
        # wait briefly for an in-flight turn so the transcript is complete
        for _ in range(50):
            if not self.busy:
                break
            time.sleep(0.05)
        if self.call_id:
            self.app.db.audit("telephony", "call_ended", self.call_id, ";".join(self.log[-10:]))


def handle_media_stream(handler, app, provider: str):
    if (handler.headers.get("Upgrade") or "").lower() != "websocket":
        return handler._send(400, {"error": "WebSocket upgrade required"})
    if provider == "exotel":
        key = os.environ.get("EXOTEL_STREAM_KEY")
        q = parse_qs(urlparse(handler.path).query)
        if not key or (q.get("key") or [""])[0] != key:
            return handler._send(403, {"error": "set EXOTEL_STREAM_KEY and pass ?key= in the Voicebot URL"})
    key = handler.headers.get("Sec-WebSocket-Key", "")
    accept = base64.b64encode(hashlib.sha1((key + GUID).encode()).digest()).decode()
    handler.send_response(101, "Switching Protocols")
    handler.send_header("Upgrade", "websocket")
    handler.send_header("Connection", "Upgrade")
    handler.send_header("Sec-WebSocket-Accept", accept)
    handler.end_headers()
    handler.wfile.flush()
    session = MediaSession(handler, app, provider)
    try:
        session.run()
    finally:
        handler.close_connection = True
    return session
