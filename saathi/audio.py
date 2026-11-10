"""WAV helpers: decode, resample to telephone quality, split for the 30 s REST limit, mix noise."""
from __future__ import annotations

import io
import wave
from typing import List, Tuple

import numpy as np

try:
    from scipy.signal import resample_poly
except Exception:  # pragma: no cover - scipy optional
    resample_poly = None


def read_wav(data: bytes) -> Tuple[np.ndarray, int]:
    """Return mono float32 samples in [-1, 1] and the sample rate."""
    with wave.open(io.BytesIO(data)) as w:
        sr = w.getframerate()
        ch = w.getnchannels()
        sw = w.getsampwidth()
        frames = w.readframes(w.getnframes())
    if sw == 2:
        x = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0
    elif sw == 1:
        x = (np.frombuffer(frames, dtype=np.uint8).astype(np.float32) - 128) / 128.0
    elif sw == 4:
        x = np.frombuffer(frames, dtype="<i4").astype(np.float32) / 2147483648.0
    else:
        raise ValueError(f"unsupported sample width {sw}")
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    return x, sr


def write_wav(x: np.ndarray, sr: int) -> bytes:
    pcm = np.clip(x, -1.0, 1.0)
    pcm = (pcm * 32767.0).astype("<i2").tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm)
    return buf.getvalue()


def resample(x: np.ndarray, sr_in: int, sr_out: int) -> np.ndarray:
    if sr_in == sr_out:
        return x
    if resample_poly is not None:
        from math import gcd
        g = gcd(sr_in, sr_out)
        return resample_poly(x, sr_out // g, sr_in // g).astype(np.float32)
    n_out = int(round(len(x) * sr_out / sr_in))
    return np.interp(np.linspace(0, len(x) - 1, n_out), np.arange(len(x)), x).astype(np.float32)


def to_telephone(data: bytes, sr_out: int = 8000) -> bytes:
    """Narrow-band phone line simulation: 8 kHz, 300-3400 Hz band, mild compression."""
    x, sr = read_wav(data)
    y = resample(x, sr, sr_out)
    try:
        from scipy.signal import butter, lfilter
        b, a = butter(4, [300 / (sr_out / 2), 3400 / (sr_out / 2)], btype="band")
        y = lfilter(b, a, y).astype(np.float32)
    except Exception:
        pass
    y = np.tanh(2.0 * y) / np.tanh(2.0)  # soft clipping like cheap handsets
    return write_wav(y, sr_out)


def pcm16_bytes(data: bytes, sr_out: int) -> bytes:
    x, sr = read_wav(data)
    y = resample(x, sr, sr_out)
    return (np.clip(y, -1, 1) * 32767).astype("<i2").tobytes()


def split_wav(data: bytes, max_seconds: float = 28.0) -> List[bytes]:
    x, sr = read_wav(data)
    step = int(max_seconds * sr)
    if len(x) <= step:
        return [data]
    return [write_wav(x[i:i + step], sr) for i in range(0, len(x), step)]


def duration_s(data: bytes) -> float:
    x, sr = read_wav(data)
    return len(x) / float(sr)


def make_noise(n: int, sr: int, kind: str = "street", seed: int = 0) -> np.ndarray:
    """Synthetic background noise (no recordings needed): pink-ish hiss, traffic rumble, horn bursts."""
    rng = np.random.default_rng(seed)
    white = rng.standard_normal(n).astype(np.float32)
    # pink-ish noise via cumulative filtering
    pink = np.cumsum(white)
    pink = pink - np.convolve(pink, np.ones(64) / 64, mode="same")
    pink /= (np.abs(pink).max() + 1e-9)
    if kind == "hiss":
        return pink
    t = np.arange(n) / sr
    rumble = 0.6 * np.sin(2 * np.pi * 70 * t) * (0.5 + 0.5 * np.sin(2 * np.pi * 0.3 * t))
    noise = 0.6 * pink + rumble
    if kind == "street":
        for _ in range(max(1, n // (sr * 4))):
            start = rng.integers(0, max(1, n - sr // 2))
            dur = int(sr * rng.uniform(0.2, 0.5))
            f = rng.uniform(380, 520)
            seg = np.arange(min(dur, n - start)) / sr
            noise[start:start + len(seg)] += 0.8 * np.sign(np.sin(2 * np.pi * f * seg))
    return (noise / (np.abs(noise).max() + 1e-9)).astype(np.float32)


def mix_at_snr(speech: np.ndarray, noise: np.ndarray, snr_db: float) -> np.ndarray:
    noise = noise[: len(speech)]
    ps = float(np.mean(speech ** 2)) + 1e-12
    pn = float(np.mean(noise ** 2)) + 1e-12
    scale = np.sqrt(ps / (pn * 10 ** (snr_db / 10)))
    out = speech + scale * noise
    peak = np.abs(out).max()
    return out / peak * 0.95 if peak > 1 else out
