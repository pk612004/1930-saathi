"""Score Gnani Prisma + the Saathi number engine on REAL volunteer recordings.

1. Start the server with COLLECT_KEY=<secret> and share /collect.html?key=<secret> with friends.
   Each volunteer reads synthetic cards (UTRs, amounts, UPI IDs, times) in their own language.
2. Then run (needs GNANI_API_KEY):
       python -m eval.run_real
   -> eval/real_report.md with per-field and per-language accuracy. This is the number to publish.
"""
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from saathi import extract as X
from saathi import numbers as N
from saathi.config import settings
from saathi.providers.gnani import PrismaSTT

NOW = datetime.now()
LANG_CODE = {"hi": "hi-IN", "en": "en-IN", "pa": "pa-IN", "ta": "ta-IN"}


def score_one(field, expected, text):
    if field == "utr":
        return N.all_digits(text) == expected
    if field == "amount":
        return N.parse_amount(text, expecting_amount=True) == int(expected)
    if field == "upi":
        got = X.extract_upi(text)
        return got == expected, X.upi_needs_spelling(text)
    if field == "time":
        return X.parse_minutes_ago(text, NOW) == int(expected)
    if field == "mobile":
        return N.all_digits(text)[-10:] == expected
    return False


def main():
    rec_dir = settings.data_dir / "recordings"
    manifest = rec_dir / "manifest.jsonl"
    if not manifest.exists():
        raise SystemExit("No recordings yet: collect some with /collect.html first.")
    stt = PrismaSTT()
    stats = defaultdict(lambda: [0, 0])
    spell_flagged = [0, 0]
    rows = []
    for line in manifest.read_text(encoding="utf-8").splitlines():
        m = json.loads(line)
        wav = (rec_dir / f"{m['id']}.wav").read_bytes()
        res = stt.transcribe(wav, language=LANG_CODE.get(m["lang"], "hi-IN"))
        out = score_one(m["field"], m["expected"], res.text)
        ok = out[0] if isinstance(out, tuple) else out
        if isinstance(out, tuple) and not out[0]:
            spell_flagged[1] += 1
            spell_flagged[0] += out[1]
        stats[(m["field"], m["lang"])][0] += ok
        stats[(m["field"], m["lang"])][1] += 1
        rows.append((m["field"], m["lang"], m["expected"], res.text, ok, round(res.latency_ms)))
    md = ["# Real recordings: Gnani Prisma + Saathi engine", "",
          f"{len(rows)} volunteer recordings of synthetic cards.", "",
          "| Field | Language | Correct | Total | Accuracy |", "|---|---|---|---|---|"]
    for (f, l), (ok, n) in sorted(stats.items()):
        md.append(f"| {f} | {l} | {ok} | {n} | {100 * ok / n:.0f}% |")
    if spell_flagged[1]:
        md += ["", f"UPI misses flagged for letter-by-letter spelling (recoverable in the call): "
                   f"{spell_flagged[0]}/{spell_flagged[1]}"]
    md += ["", "| Field | Lang | Expected | Prisma heard | OK | ms |", "|---|---|---|---|---|---|"]
    md += [f"| {f} | {l} | {e} | {t} | {'✅' if ok else '❌'} | {ms} |" for f, l, e, t, ok, ms in rows]
    Path(__file__).with_name("real_report.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md[:12 + len(stats)]))


if __name__ == "__main__":
    main()
