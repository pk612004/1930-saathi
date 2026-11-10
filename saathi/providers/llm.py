"""Evon v3.3 (Gnani's open-weight reasoning model) through an OpenAI-compatible endpoint.

Evon is not on Gnani's hosted API yet; its weights are on Hugging Face
(gnani/gnani-evon-v3.3-30B-A3B, Apache 2.0). Serve it with vLLM or a Hugging
Face Inference Endpoint, e.g.

    vllm serve gnani/gnani-evon-v3.3-30B-A3B --max-model-len 8192

and set EVON_BASE_URL=http://<host>:8000/v1.

The agent never *depends* on the LLM: every slot is captured and validated by
deterministic code. Evon adds (1) an officer-facing case summary and (2) a
second opinion on the fraud pattern when the keyword rules return "other".
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from typing import Dict, Optional

from ..config import settings
from ..extract import FRAUD_TYPES


class EvonLLM:
    name = "gnani-evon-v3.3"

    def __init__(self, base_url: str = "", model: str = "", api_key: str = "", timeout: float = 12.0):
        self.base_url = (base_url or settings.evon_base_url).rstrip("/")
        self.model = model or settings.evon_model
        self.api_key = api_key or settings.evon_api_key
        self.timeout = timeout

    def chat(self, system: str, user: str, max_tokens: int = 200, temperature: float = 0.1) -> Dict:
        body = {"model": self.model, "max_tokens": max_tokens, "temperature": temperature,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(f"{self.base_url}/chat/completions", data=json.dumps(body).encode(),
                                     headers=headers, method="POST")
        t0 = time.perf_counter()
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
        text = data["choices"][0]["message"]["content"]
        # reasoning models may wrap thoughts; keep the final answer
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
        return {"text": text, "latency_ms": (time.perf_counter() - t0) * 1000}

    def summarize(self, case_dict: Dict) -> Optional[Dict]:
        system = ("You write two-sentence summaries of cyber-fraud complaints for Indian police officers. "
                  "Use only facts given. No speculation. English.")
        facts = {k: case_dict.get(k) for k in ("fraud_label", "narrative", "total_amount", "live_threat",
                                                "victim_bank")}
        facts["transactions"] = [{k: t.get(k) for k in ("amount", "minutes_ago", "mode", "utr")}
                                 for t in case_dict.get("transactions", [])]
        facts["suspect"] = case_dict.get("suspect")
        try:
            out = self.chat(system, json.dumps(facts, ensure_ascii=False))
            return {"summary": out["text"], "latency_ms": out["latency_ms"], "source": self.name}
        except (urllib.error.URLError, OSError, KeyError, ValueError):
            return None

    def classify(self, narrative: str) -> Optional[str]:
        labels = {k: v["label"] for k, v in FRAUD_TYPES.items()}
        system = ("Classify an Indian cyber-fraud victim's narrative (Hindi, Hinglish or English) into exactly one "
                  "label key. Reply with JSON {\"label\": \"<key>\"}. Keys: " + json.dumps(labels) +
                  " or \"other\".")
        try:
            out = self.chat(system, narrative, max_tokens=30)
            m = re.search(r"\{.*\}", out["text"], flags=re.S)
            key = json.loads(m.group(0))["label"] if m else out["text"].strip()
            return key if key in FRAUD_TYPES else None
        except (urllib.error.URLError, OSError, KeyError, ValueError, AttributeError):
            return None


    SLOT_SPECS = {
        "amount": 'the amount of money lost in Indian rupees, as an integer. {"value": 45000}',
        "time": 'how many minutes ago the money was debited, as an integer. {"value": 30}',
        "utr": 'the 12-digit UPI/IMPS transaction reference (UTR/RRN), digits only. {"value": "412356789012"}',
        "suspect": 'the fraudster\'s UPI ID, mobile number or bank account. {"upi": "name@handle" or null, '
                   '"mobile": "10 digits" or null, "account": "digits" or null}',
        "bank": 'the caller\'s own bank name in English, e.g. {"value": "State Bank of India"}',
        "mode": 'payment mode, one of UPI, Card, Net banking / IMPS / NEFT, Wallet. {"value": "UPI"}',
    }

    def extract_slot(self, slot: str, utterance: str, lang: str = "hi") -> Optional[Dict]:
        """Ask Evon for ONE field as strict JSON. The caller must still pass the code validators."""
        spec = self.SLOT_SPECS.get(slot)
        if not spec:
            return None
        system = ("You extract one field from what an Indian cyber-fraud victim said on a phone call "
                  "(Hindi, Hinglish, Punjabi, Tamil or English; the transcript may be in Devanagari). "
                  f"Field: {spec} If the field is not clearly present, reply {{\"value\": null}}. "
                  "Reply with JSON only. Never guess digits that were not said.")
        try:
            out = self.chat(system, utterance, max_tokens=60, temperature=0.0)
            m = re.search(r"\{.*\}", out["text"], flags=re.S)
            if not m:
                return None
            data = json.loads(m.group(0))
            data["_latency_ms"] = out["latency_ms"]
            return data
        except (urllib.error.URLError, OSError, KeyError, ValueError):
            return None


class NoLLM:
    name = "rules"

    def extract_slot(self, slot: str, utterance: str, lang: str = "hi") -> Optional[Dict]:
        return None

    def summarize(self, case_dict: Dict) -> Optional[Dict]:
        return None

    def classify(self, narrative: str) -> Optional[str]:
        return None


def make_llm():
    return EvonLLM() if settings.evon_live else NoLLM()
