"""Evaluate 1930 Saathi on synthetic calls.

Text mode (default, runs anywhere):
    python -m eval.run_eval --calls 300 --asr-error 0.25

    Feeds the scripted caller's words straight into the engine. --asr-error
    simulates speech-recognition slips on number-bearing utterances (a digit
    substituted, dropped or inserted), so we can measure how much the
    validator + read-back loop recovers. These are SIMULATED errors.

Audio mode (needs GNANI_API_KEY):
    python -m eval.run_eval --audio --calls 30 --snr 10

    Every caller line is synthesised with Gnani Timbre, converted to 8 kHz
    telephone audio, mixed with synthetic street noise at the given SNR, then
    transcribed by Gnani Prisma before reaching the engine. This is the real
    end-to-end number to publish.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import statistics
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

from saathi import numbers as N
from saathi.dialog import Dialog

from .scenarios import CallerSim, disfluent, make_call

ROOT = Path(__file__).resolve().parent
NOW = datetime(2026, 11, 6, 13, 0)
DIGIT_STATES = {"utr", "utr_confirm", "suspect", "suspect_confirm"}


def corrupt_digits(text: str, rng: random.Random) -> str:
    """Simulate one ASR slip inside a number: substitute, drop or insert a digit token."""
    toks = text.split(" ")
    idx = [i for i, t in enumerate(toks) if re.fullmatch(r"\d+", t) or t in N.WORD_TO_NUM]
    if not idx:
        return text
    i = rng.choice(idx)
    tok = toks[i]
    op = rng.choice(["sub", "sub", "drop", "insert"])
    if re.fullmatch(r"\d+", tok):
        pos = rng.randrange(len(tok))
        if op == "sub":
            tok = tok[:pos] + str((int(tok[pos]) + rng.randrange(1, 10)) % 10) + tok[pos + 1:]
        elif op == "drop":
            tok = tok[:pos] + tok[pos + 1:]
        else:
            tok = tok[:pos] + str(rng.randrange(10)) + tok[pos:]
        toks[i] = tok
    else:
        if op == "drop":
            toks.pop(i)
        elif op == "insert":
            toks.insert(i, str(rng.randrange(10)))
        else:
            toks[i] = str((N.WORD_TO_NUM[tok] + rng.randrange(1, 10)) % 10) if N.WORD_TO_NUM[tok] < 10 else tok
    return " ".join(t for t in toks if t)


def words(s: str) -> int:
    return len(s.split())


class AudioPipe:
    """Timbre -> telephone 8 kHz -> noise -> Prisma (live only)."""

    def __init__(self, snr_db: float, seed: int):
        from saathi.providers.gnani import PrismaSTT, TimbreTTS
        from saathi.config import settings
        if not settings.gnani_api_key:
            raise SystemExit("Audio mode needs GNANI_API_KEY (in .env).")
        self.tts = TimbreTTS(voice=settings.timbre_voice)
        self.stt = PrismaSTT()
        self.snr = snr_db
        self.seed = seed
        self.latencies = []

    def __call__(self, text: str, lang: str, i: int) -> str:
        from saathi import audio as A
        wav = self.tts.synthesize(text, language="en-IN" if lang == "en" else "hi-IN")["audio"]
        phone = A.to_telephone(wav, 8000)
        x, sr = A.read_wav(phone)
        noisy = A.mix_at_snr(x, A.make_noise(len(x), sr, "street", self.seed + i), self.snr)
        res = self.stt.transcribe(A.write_wav(noisy, sr), language="en-IN" if lang == "en" else "hi-IN")
        self.latencies.append(res.latency_ms)
        return res.text


def run(n_calls: int, asr_error: float, seed: int, audio=None, max_turns: int = 40, disfluency: bool = False):
    rng = random.Random(seed)
    stats = Counter()
    per_field = Counter()
    turns, talk_s = [], []
    utr_first_ok = utr_final_ok = utr_total = utr_wrong_filed = utr_unknown = 0
    sus_first_ok = sus_final_ok = 0
    threat_tp = threat_fn = threat_fp = threat_tn = 0
    failures = []
    by_lang = {}
    t0 = time.perf_counter()
    for k in range(n_calls):
        truth = make_call(rng)
        sim = CallerSim(truth, random.Random(truth.style_seed))
        d = Dialog(now_fn=lambda: NOW, lang=None)
        g = d.greeting()
        agent_words = words(g.text)
        caller_words = 0
        n_turns = 0
        noise_rng = random.Random(truth.style_seed + 7)
        while d.state != "done" and n_turns < max_turns:
            utter = sim.answer(d.state, d)
            if disfluency:
                utter = disfluent(utter, truth.lang, noise_rng)
            spoken = utter
            if audio is not None:
                spoken = audio(utter, truth.lang, k * 100 + n_turns)
            elif asr_error and d.state in DIGIT_STATES and noise_rng.random() < asr_error:
                spoken = corrupt_digits(utter, noise_rng)
                stats["asr_errors_injected"] += 1
            caller_words += words(utter)
            r = d.step(spoken)
            agent_words += words(r.text)
            n_turns += 1
        c = d.case
        stats["calls"] += 1
        stats["filed"] += c.status == "filed"
        turns.append(n_turns)
        # ~2.4 words/s for both sides + 0.8 s turn-taking gap
        talk_s.append((agent_words + caller_words) / 2.4 + 0.8 * n_turns)

        # field accuracy (first transaction carries the golden-hour decision)
        tt = truth.txns[0]
        ct = c.transactions[0]
        per_field["amount"] += ct.amount == tt.amount
        per_field["minutes"] += ct.minutes_ago == tt.minutes
        per_field["mode"] += (ct.mode == tt.mode) or (ct.mode == "UPI" and truth.suspect_kind == "upi")
        heard_sus = c.suspect.upi or c.suspect.mobile or c.suspect.account
        per_field["suspect"] += heard_sus == truth.suspect
        sus_first_ok += c.suspect.first_heard == truth.suspect
        per_field["bank"] += c.victim_bank == truth.bank
        per_field["fraud_type"] += c.fraud_type == truth.fraud_type
        per_field["txn_count"] += len(c.transactions) == len(truth.txns)
        if tt.utr:
            utr_total += 1
            utr_first_ok += ct.utr_first_heard == tt.utr
            utr_final_ok += ct.utr == tt.utr
            utr_wrong_filed += bool(ct.utr) and ct.utr != tt.utr
            utr_unknown += ct.utr is None
        bl = by_lang.setdefault(truth.lang, Counter())
        bl["calls"] += 1
        bl["filed"] += c.status == "filed"
        bl["amount"] += ct.amount == tt.amount
        bl["suspect"] += heard_sus == truth.suspect
        bl["bank"] += c.victim_bank == truth.bank
        bl["fraud_type"] += c.fraud_type == truth.fraud_type
        if tt.utr:
            bl["utr_calls"] += 1
            bl["utr_ok"] += ct.utr == tt.utr
            bl["utr_wrong"] += bool(ct.utr) and ct.utr != tt.utr
        if truth.live_threat:
            threat_tp += c.live_threat
            threat_fn += not c.live_threat
        else:
            threat_fp += c.live_threat
            threat_tn += not c.live_threat
        if c.status != "filed" or heard_sus != truth.suspect or ct.amount != tt.amount:
            if len(failures) < 8:
                failures.append({"truth": truth.__dict__ | {"txns": [t.__dict__ for t in truth.txns]},
                                 "transcript": [(t.role, t.text) for t in c.transcript]})
    n = stats["calls"]
    pct = lambda a, b: round(100.0 * a / b, 1) if b else None
    report = {
        "mode": "audio (Timbre -> 8 kHz + noise -> Prisma)" if audio else "text (simulated ASR errors)",
        "calls": n,
        "seed": seed,
        "simulated_asr_error_rate_on_number_turns": None if audio else asr_error,
        "asr_errors_injected": stats["asr_errors_injected"],
        "filed_pct": pct(stats["filed"], n),
        "field_accuracy_pct": {k: pct(v, n) for k, v in per_field.items()},
        "utr": {
            "calls_with_utr": utr_total,
            "first_heard_correct_pct": pct(utr_first_ok, utr_total),
            "final_correct_pct": pct(utr_final_ok, utr_total),
            "wrong_utr_filed_pct": pct(utr_wrong_filed, utr_total),
            "left_unknown_pct": pct(utr_unknown, utr_total),
        },
        "suspect_id": {"first_heard_correct_pct": pct(sus_first_ok, n), "final_correct_pct": pct(per_field["suspect"], n)},
        "live_threat": {"recall_pct": pct(threat_tp, threat_tp + threat_fn),
                        "false_positive_pct": pct(threat_fp, threat_fp + threat_tn),
                        "threat_calls": threat_tp + threat_fn},
        "turns_per_call": {"mean": round(statistics.mean(turns), 1), "p90": sorted(turns)[int(0.9 * (len(turns) - 1))]},
        "estimated_call_seconds": {"mean": round(statistics.mean(talk_s)), "p90": round(sorted(talk_s)[int(0.9 * (len(talk_s) - 1))])},
        "engine_wall_ms_per_call": round((time.perf_counter() - t0) * 1000 / max(n, 1), 2),
        "disfluency": disfluency,
        "by_language": {L: {"calls": b["calls"], "filed_pct": pct(b["filed"], b["calls"]),
                            "amount_pct": pct(b["amount"], b["calls"]), "suspect_pct": pct(b["suspect"], b["calls"]),
                            "bank_pct": pct(b["bank"], b["calls"]), "fraud_type_pct": pct(b["fraud_type"], b["calls"]),
                            "utr_final_pct": pct(b["utr_ok"], b["utr_calls"]),
                            "wrong_utr_filed_pct": pct(b["utr_wrong"], b["utr_calls"])}
                        for L, b in sorted(by_lang.items())},
    }
    if audio:
        report["prisma_latency_ms"] = {"mean": round(statistics.mean(audio.latencies)),
                                       "p90": round(sorted(audio.latencies)[int(0.9 * (len(audio.latencies) - 1))])}
    return report, failures


def to_markdown(reports) -> str:
    lines = ["# 1930 Saathi evaluation", "",
             "All calls are synthetic (random amounts, UTRs, UPI IDs and phone numbers).",
             "Text-mode numbers measure the understanding + dialog layer with *simulated* recognition errors;",
             "audio-mode numbers (when present) include real Gnani Timbre -> 8 kHz noisy audio -> Gnani Prisma.", ""]
    for r in reports:
        lines += [f"## {r['mode']} · {r['calls']} calls" + (" · disfluent speech (fillers, digit stutters)" if r.get("disfluency") else "")
                  + (f" · simulated digit-error rate {r['simulated_asr_error_rate_on_number_turns']}" if r.get(
                      "simulated_asr_error_rate_on_number_turns") is not None else ""), ""]
        lines += ["| Metric | Value |", "|---|---|",
                  f"| Complaints filed | {r['filed_pct']}% |",
                  f"| UTR correct as first heard | {r['utr']['first_heard_correct_pct']}% |",
                  f"| UTR correct after validator + read-back | **{r['utr']['final_correct_pct']}%** |",
                  f"| Wrong UTR filed | {r['utr']['wrong_utr_filed_pct']}% |",
                  f"| UTR left 'not known' (safe fallback) | {r['utr']['left_unknown_pct']}% |",
                  f"| Fraudster ID correct, first heard → final | {r['suspect_id']['first_heard_correct_pct']}% → **{r['suspect_id']['final_correct_pct']}%** |",
                  f"| Amount / time / bank correct | {r['field_accuracy_pct']['amount']}% / {r['field_accuracy_pct']['minutes']}% / {r['field_accuracy_pct']['bank']}% |",
                  f"| Fraud pattern correct | {r['field_accuracy_pct']['fraud_type']}% |",
                  f"| Live-threat recall / false positives | {r['live_threat']['recall_pct']}% / {r['live_threat']['false_positive_pct']}% |",
                  f"| Turns per call (mean / p90) | {r['turns_per_call']['mean']} / {r['turns_per_call']['p90']} |",
                  f"| Estimated call length (mean / p90) | {r['estimated_call_seconds']['mean']} s / {r['estimated_call_seconds']['p90']} s |",
                  ]
        lines += ["", "| Language (transcript style) | Calls | Filed | Amount | UTR final | Wrong UTR | Fraudster ID | Bank | Fraud type |",
                  "|---|---|---|---|---|---|---|---|---|"]
        names = {"hi": "Hinglish (Latin)", "dev": "Hindi (Devanagari, like Prisma hi-IN)", "en": "English",
                 "pa": "Punjabi (Gurmukhi)", "ta": "Tamil (Tamil script)"}
        for L, b in r["by_language"].items():
            lines.append(f"| {names.get(L, L)} | {b['calls']} | {b['filed_pct']}% | {b['amount_pct']}% | {b['utr_final_pct']}% | "
                         f"{b['wrong_utr_filed_pct']}% | {b['suspect_pct']}% | {b['bank_pct']}% | {b['fraud_type_pct']}% |")
        if r.get("prisma_latency_ms"):
            lines.append(f"| Prisma latency (mean / p90) | {r['prisma_latency_ms']['mean']} / {r['prisma_latency_ms']['p90']} ms |")
        lines.append("")
    lines += ["Estimated call length assumes 2.4 spoken words per second for both sides plus 0.8 s per turn.", ""]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--calls", type=int, default=300)
    ap.add_argument("--asr-error", type=float, nargs="*", default=[0.0, 0.25])
    ap.add_argument("--seed", type=int, default=1930)
    ap.add_argument("--audio", action="store_true")
    ap.add_argument("--snr", type=float, default=10.0)
    ap.add_argument("--out", default=str(ROOT / "report"))
    ap.add_argument("--disfluency", action="store_true", help="add fillers and digit stutters")
    args = ap.parse_args()
    reports, all_fail = [], []
    if args.audio:
        rep, fails = run(args.calls, 0.0, args.seed, audio=AudioPipe(args.snr, args.seed))
        rep["snr_db"] = args.snr
        reports.append(rep)
        all_fail += fails
    else:
        for e in args.asr_error:
            rep, fails = run(args.calls, e, args.seed, disfluency=args.disfluency)
            reports.append(rep)
            all_fail += fails
    Path(args.out + ".json").write_text(json.dumps(reports, indent=2, ensure_ascii=False))
    Path(args.out + ".md").write_text(to_markdown(reports), encoding="utf-8")
    Path(args.out + "_failures.json").write_text(json.dumps(all_fail, indent=1, ensure_ascii=False))
    print(to_markdown(reports))


if __name__ == "__main__":
    main()
