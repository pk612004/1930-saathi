"""Configuration from environment variables or a local .env file."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path):
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv(ROOT / ".env")


@dataclass
class Settings:
    gnani_api_key: str = os.environ.get("GNANI_API_KEY", "")
    gnani_base_url: str = os.environ.get("GNANI_BASE_URL", "https://api.vachana.ai")
    gnani_ws_url: str = os.environ.get("GNANI_WS_URL", "wss://api.vachana.ai")
    # The API sits behind Cloudflare, which rejects Python's default "Python-urllib" agent (error 1010).
    user_agent: str = os.environ.get("GNANI_USER_AGENT",
                                     "Mozilla/5.0 (Windows NT 10.0; Win64; x64) 1930-Saathi/2.2 (+student prototype)")
    prisma_model: str = os.environ.get("PRISMA_MODEL", "")            # "" = Prisma v2.5 default, or prisma-v3.0
    stt_language: str = os.environ.get("STT_LANGUAGE", "hi-IN")
    stt_realtime: bool = os.environ.get("STT_REALTIME", "0") == "1"
    timbre_model: str = os.environ.get("TIMBRE_MODEL", "timbre-v2.5")
    timbre_voice: str = os.environ.get("TIMBRE_VOICE", "Nalini")
    tts_sample_rate: int = int(os.environ.get("TTS_SAMPLE_RATE", "16000"))
    evon_base_url: str = os.environ.get("EVON_BASE_URL", "")          # OpenAI-compatible, e.g. http://localhost:8000/v1
    evon_model: str = os.environ.get("EVON_MODEL", "gnani/gnani-evon-v3.3-30B-A3B")
    evon_api_key: str = os.environ.get("EVON_API_KEY", "")
    mode: str = os.environ.get("SAATHI_MODE", "auto")                 # auto | mock | live
    host: str = os.environ.get("HOST", "127.0.0.1")
    port: int = int(os.environ.get("PORT", "8930"))
    data_dir: Path = ROOT / "data"

    @property
    def gnani_live(self) -> bool:
        if self.mode == "mock":
            return False
        return bool(self.gnani_api_key)

    @property
    def evon_live(self) -> bool:
        if self.mode == "mock":
            return False
        return bool(self.evon_base_url)


settings = Settings()
