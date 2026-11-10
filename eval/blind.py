"""Second held-out set, written after the stress-set fixes and NOT tuned on.

Its score is the honest estimate of how the number engine handles phrasing it
has never seen.    python -m eval.blind
"""
from datetime import datetime

from saathi import extract as X
from saathi import numbers as N

NOW = datetime(2026, 11, 6, 13, 0)
CASES = [
    ("amount", "saath hazaar rupaye", 60000),
    ("amount", "bas 800 rupaye", 800),
    ("amount", "do hazaar teen sau", 2300),
    ("amount", "ek lakh pachchis hazaar", 125000),
    ("amount", "fifteen thousand", 15000),
    ("amount", "1.75 lakh", 175000),
    ("amount", "teen hazaar nau sau ninyanve", 3999),
    ("digits", "paanch paanch paanch, chaar chaar chaar, teen teen teen, do do do", "555444333222"),
    ("digits", "seven seven two zero, one one nine eight, three four five six", "772011983456"),
    ("digits", "number hai 9 9 9 9 9, 0 0 0 0 1", "9999900001"),
    ("digits", "छह छह सात सात आठ आठ नौ नौ एक एक दो दो", "667788991122"),
    ("upi", "priya dot sharma 99 at the rate okicici", "priya.sharma99@okicici"),
    ("upi", "help desk at the rate axl", "helpdesk@axl"),
    ("time", "pichhle aadhe ghante mein", 30),
    ("time", "2 baje dopahar", 1380),   # 14:00 is after 13:00 "now", so it means yesterday
    ("time", "teen ghante pehle", 180),
]


def run():
    rows = []
    for kind, text, exp in CASES:
        got = {"amount": lambda: N.parse_amount(text, expecting_amount=True),
               "digits": lambda: N.all_digits(text),
               "upi": lambda: X.extract_upi(text),
               "time": lambda: X.parse_minutes_ago(text, NOW)}[kind]()
        rows.append((kind, text, exp, got))
    ok = sum(r[2] == r[3] for r in rows)
    md = [f"# Blind held-out set: {ok}/{len(rows)} correct ({100 * ok / len(rows):.0f}%)", "",
          "| Type | Caller said | Expected | Got | |", "|---|---|---|---|---|"]
    md += [f"| {k} | {t} | {e} | {g} | {'✅' if e == g else '❌'} |" for k, t, e, g in rows]
    return ok, len(rows), "\n".join(md)


if __name__ == "__main__":
    from pathlib import Path
    ok, n, md = run()
    Path(__file__).with_name("blind_report.md").write_text(md + "\n", encoding="utf-8")
    print(md)
