"""Gnani client request formats, checked against a local fake of the documented API."""
import pytest

from saathi.providers.gnani import PrismaRealtimeSTT, PrismaSTT, ProviderError, TimbreTTS
from saathi.providers.ws import OP_TEXT, decode_frame, encode_frame

from . import fake_gnani as F


@pytest.fixture(scope="module")
def fake():
    http, ws = F.start()
    yield f"http://127.0.0.1:{http.server_address[1]}", f"ws://127.0.0.1:{ws.server_address[1]}"
    http.shutdown()
    ws.shutdown()


def test_prisma_rest(fake):
    base, _ = fake
    stt = PrismaSTT(api_key=F.API_KEY, base_url=base, model="", language="hi-IN")
    res = stt.transcribe(F.tiny_wav(1.0, 8000))
    assert res.text == F.TRANSCRIPT and res.provider == "gnani-prisma"
    assert F.SEEN["stt_ctype"].startswith("multipart/form-data")
    assert F.SEEN["stt_has_audio_file"] and F.SEEN["stt_has_language"]


def test_prisma_rest_bad_key(fake):
    base, _ = fake
    with pytest.raises(ProviderError):
        PrismaSTT(api_key="wrong", base_url=base).transcribe(F.tiny_wav())


def test_timbre(fake, tmp_path):
    base, _ = fake
    tts = TimbreTTS(api_key=F.API_KEY, base_url=base, voice="Nalini", sample_rate=16000, cache_dir=tmp_path)
    out = tts.synthesize("नमस्ते", language="hi-IN")
    assert out["audio"][:4] == b"RIFF" and not out["cached"]
    body = F.SEEN["tts_body"]
    assert body["text"] == "नमस्ते" and body["voice"] == "Nalini" and body["model"] == "timbre-v2.5"
    assert body["audio_config"] == {"sample_rate": 16000, "num_channels": 1, "sample_width": 2,
                                    "encoding": "linear_pcm", "container": "wav"}
    assert tts.synthesize("नमस्ते", language="hi-IN")["cached"]


def test_prisma_realtime(fake):
    _, ws = fake
    stt = PrismaRealtimeSTT(api_key=F.API_KEY, ws_url=ws, language="hi-IN", sample_rate=8000)
    res = stt.transcribe(F.tiny_wav(1.0, 16000))
    assert res.text == "मेरे 45 हज़ार रुपये कट गए"     # latest text per segment, in order
    h = F.SEEN["ws_headers"]
    assert h["x-api-key-id"] == F.API_KEY and h["language_code"] == "hi-IN" and h["x-sample-rate"] == "8000"
    assert F.SEEN["ws_frames"] == 16 and F.SEEN["ws_max_frame"] == 1024   # 1 s of 8 kHz 16-bit = 16000 B


def test_ws_frame_roundtrip():
    for size in (5, 300, 70000):
        payload = bytes(range(256)) * (size // 256 + 1)
        payload = payload[:size]
        frame = encode_frame(OP_TEXT, payload, mask=True)
        buf = [frame]

        def read_exact(n):
            out, buf[0] = buf[0][:n], buf[0][n:]
            return out
        fin, op, out = decode_frame(read_exact)
        assert fin and op == OP_TEXT and out == payload
