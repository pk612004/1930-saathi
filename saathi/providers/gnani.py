"""Gnani AI clients: Prisma (speech-to-text) and Timbre (text-to-speech).

Endpoints and field names follow Gnani's developer docs (docs.gnani.ai,
quick start): base URL https://api.vachana.ai, auth header X-API-Key-ID.

* Prisma REST       POST /stt/v3            multipart: audio_file, model, language_code
* Prisma realtime   wss  /stt/v3/stream     headers: x-api-key-id, model, language_code, x-sample-rate
                                            body: 16-bit mono PCM frames of 1024 bytes, then {"type":"commit"}
* Timbre REST       POST /api/v1/tts/inference  JSON: text, voice, model, language, speed, audio_config

Mock providers are used when no API key is configured, and they say so in
every response (`provider: "mock"`), so a demo can never pass mock output
off as Gnani output.
"""
from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .. import audio
from ..config import settings
from .ws import OP_BINARY, OP_CLOSE, OP_TEXT, WebSocket, WebSocketError


@dataclass
class STTResult:
    text: str
    provider: str
    latency_ms: float
    model: str = ""
    detected_language: Optional[str] = None
    raw: Dict = field(default_factory=dict)
    error: Optional[str] = None


class ProviderError(Exception):
    pass


def _multipart(fields: Dict[str, str], files: Dict[str, tuple]) -> tuple:
    boundary = "----saathi" + uuid.uuid4().hex
    body = bytearray()
    for k, v in fields.items():
        body += f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode()
    for k, (filename, content, ctype) in files.items():
        body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"; filename=\"{filename}\"\r\n"
                 f"Content-Type: {ctype}\r\n\r\n").encode()
        body += content + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    return bytes(body), f"multipart/form-data; boundary={boundary}"


class PrismaSTT:
    """Prisma speech-to-text over REST (files up to 30 s; longer audio is split)."""

    name = "gnani-prisma"

    def __init__(self, api_key: str = "", base_url: str = "", model: str = "", language: str = ""):
        self.api_key = api_key or settings.gnani_api_key
        self.base_url = (base_url or settings.gnani_base_url).rstrip("/")
        self.model = model if model is not None else settings.prisma_model
        self.language = language or settings.stt_language

    def _one(self, wav: bytes, language: str) -> Dict:
        fields = {"language_code": language}
        if self.model:
            fields["model"] = self.model
        body, ctype = _multipart(fields, {"audio_file": ("call.wav", wav, "audio/wav")})
        req = urllib.request.Request(f"{self.base_url}/stt/v3", data=body, method="POST",
                                     headers={"X-API-Key-ID": self.api_key, "Content-Type": ctype, "User-Agent": settings.user_agent,
                                              "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise ProviderError(f"Prisma HTTP {e.code}: {e.read()[:300]!r}") from e
        except urllib.error.URLError as e:
            raise ProviderError(f"Prisma unreachable: {e.reason}") from e

    def transcribe(self, wav: bytes, language: Optional[str] = None) -> STTResult:
        language = language or self.language
        t0 = time.perf_counter()
        texts: List[str] = []
        raw = {}
        for chunk in audio.split_wav(wav, 28.0):
            raw = self._one(chunk, language)
            if raw.get("success") is False:
                raise ProviderError(f"Prisma error: {raw}")
            texts.append(raw.get("transcript", ""))
        return STTResult(text=" ".join(t for t in texts if t).strip(), provider=self.name,
                         latency_ms=(time.perf_counter() - t0) * 1000, model=raw.get("model", self.model or "prisma-v2.5"),
                         detected_language=raw.get("detected_language_code"), raw=raw)


class PrismaRealtimeSTT:
    """Prisma realtime over WebSocket: stream PCM frames, then commit."""

    name = "gnani-prisma-realtime"

    def __init__(self, api_key: str = "", ws_url: str = "", model: str = "", language: str = "",
                 sample_rate: int = 8000):
        self.api_key = api_key or settings.gnani_api_key
        self.ws_url = (ws_url or settings.gnani_ws_url).rstrip("/") + "/stt/v3/stream"
        self.model = model or settings.prisma_model
        self.language = language or settings.stt_language
        self.sample_rate = sample_rate

    def transcribe(self, wav: bytes, language: Optional[str] = None, realtime_pacing: bool = False) -> STTResult:
        pcm = audio.pcm16_bytes(wav, self.sample_rate)
        headers = {"x-api-key-id": self.api_key, "user-agent": settings.user_agent, "language_code": language or self.language,
                   "x-sample-rate": str(self.sample_rate)}
        if self.model:
            headers["model"] = self.model
        t0 = time.perf_counter()
        first_partial_ms = None
        segments: Dict[str, str] = {}
        order: List[str] = []
        ws = WebSocket(self.ws_url, headers, timeout=15)
        try:
            ws.connect()
            frame = 1024
            for i in range(0, len(pcm), frame):
                ws.send_binary(pcm[i:i + frame])
                if realtime_pacing:
                    time.sleep(frame / 2 / self.sample_rate)
            ws.send_text(json.dumps({"type": "commit"}))
            ws.settimeout(8)
            while True:
                try:
                    op, payload = ws.recv()
                except (OSError, WebSocketError):
                    break
                if op == OP_CLOSE:
                    break
                if op not in (OP_TEXT, OP_BINARY):
                    continue
                try:
                    msg = json.loads(payload.decode("utf-8"))
                except ValueError:
                    continue
                if msg.get("type") == "error":
                    raise ProviderError(f"Prisma realtime error: {msg.get('message')}")
                if msg.get("type") == "transcript" or "text" in msg:
                    seg = str(msg.get("segment_id", len(order)))
                    if seg not in segments:
                        order.append(seg)
                    segments[seg] = msg.get("text", "")
                    if first_partial_ms is None:
                        first_partial_ms = (time.perf_counter() - t0) * 1000
                    if msg.get("is_final") and msg.get("type") == "final":
                        break
        except (OSError, WebSocketError) as e:
            raise ProviderError(f"Prisma realtime unreachable: {e}") from e
        finally:
            ws.close()
        text = " ".join(segments[s] for s in order if segments[s]).strip()
        return STTResult(text=text, provider=self.name, latency_ms=(time.perf_counter() - t0) * 1000,
                         model=self.model or "prisma-v2.5",
                         raw={"first_transcript_ms": first_partial_ms, "segments": len(order)})


class MockSTT:
    """No speech recognition: the caller simulator sends typed text instead."""

    name = "mock"

    def transcribe(self, wav: bytes, language: Optional[str] = None) -> STTResult:
        return STTResult(text="", provider=self.name, latency_ms=0.0,
                         error="Mock mode: add GNANI_API_KEY to transcribe audio with Prisma, or type the caller's words.")


class TimbreTTS:
    name = "gnani-timbre"

    def __init__(self, api_key: str = "", base_url: str = "", model: str = "", voice: str = "",
                 sample_rate: int = 0, cache_dir=None):
        self.api_key = api_key or settings.gnani_api_key
        self.base_url = (base_url or settings.gnani_base_url).rstrip("/")
        self.model = model or settings.timbre_model
        self.voice = voice or settings.timbre_voice
        self.sample_rate = sample_rate or settings.tts_sample_rate
        self.cache_dir = cache_dir or (settings.data_dir / "tts_cache")
        self._mem: Dict[str, bytes] = {}

    def _key(self, text: str, language: str, voice: str, speed: float) -> str:
        return hashlib.sha1(f"{self.model}|{voice}|{language}|{speed}|{self.sample_rate}|{text}".encode()).hexdigest()

    def synthesize(self, text: str, language: str = "hi-IN", voice: Optional[str] = None,
                   speed: float = 1.0) -> Dict:
        voice = voice or self.voice
        key = self._key(text, language, voice, speed)
        if key in self._mem:
            return {"audio": self._mem[key], "provider": self.name, "latency_ms": 0.0, "cached": True}
        path = self.cache_dir / f"{key}.wav"
        if path.exists():
            data = path.read_bytes()
            self._mem[key] = data
            return {"audio": data, "provider": self.name, "latency_ms": 0.0, "cached": True}
        body = {
            "text": text, "voice": voice, "model": self.model, "language": language, "speed": speed,
            "audio_config": {"sample_rate": self.sample_rate, "num_channels": 1, "sample_width": 2,
                             "encoding": "linear_pcm", "container": "wav"},
        }
        req = urllib.request.Request(f"{self.base_url}/api/v1/tts/inference",
                                     data=json.dumps(body).encode("utf-8"), method="POST",
                                     headers={"X-API-Key-ID": self.api_key, "Content-Type": "application/json",
                                              "User-Agent": settings.user_agent, "Accept": "audio/wav, */*"})
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = r.read()
                ctype = r.headers.get("Content-Type", "")
        except urllib.error.HTTPError as e:
            raise ProviderError(f"Timbre HTTP {e.code}: {e.read()[:300]!r}") from e
        except urllib.error.URLError as e:
            raise ProviderError(f"Timbre unreachable: {e.reason}") from e
        if "json" in ctype:
            raise ProviderError(f"Timbre returned JSON instead of audio: {data[:300]!r}")
        self._mem[key] = data
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        except OSError:
            pass
        return {"audio": data, "provider": self.name, "latency_ms": (time.perf_counter() - t0) * 1000, "cached": False}


class MockTTS:
    name = "mock"

    def synthesize(self, text: str, language: str = "hi-IN", voice: Optional[str] = None, speed: float = 1.0) -> Dict:
        return {"audio": None, "provider": self.name, "latency_ms": 0.0,
                "note": "Mock mode: browser voice used for preview. Add GNANI_API_KEY for Timbre."}


def make_stt():
    if not settings.gnani_live:
        return MockSTT()
    if settings.stt_realtime:
        return PrismaRealtimeSTT()
    return PrismaSTT()


def make_tts():
    return TimbreTTS() if settings.gnani_live else MockTTS()
