"""Held-out stress set: tricky ways real callers say things.

These phrasings were written separately from the generator in scenarios.py,
to check the number engine is not just fitted to its own templates. Failures
are reported, not hidden.

    python -m eval.stress
"""
from __future__ import annotations

from datetime import datetime

from saathi import extract as X
from saathi import numbers as N

NOW = datetime(2026, 11, 6, 13, 0)

AMOUNTS = [
    ("umm ji mere pachas hazaar gaye", 50000),
    ("kareeb 45 hazaar", 45000),
    ("chalis hazaar paanch sau", 40500),
    ("Rs. 9,999", 9999),
    ("teen lakh", 300000),
    ("साढ़े चार हज़ार", 4500),
    ("डेढ़ लाख रुपये", 150000),
    ("ek lakh das hazaar", 110000),
    ("pachchis hazaar rupaiye", 25000),
    ("twelve thousand five hundred", 12500),
    ("2.5 lakh", 250000),
    ("ninety nine thousand", 99000),
    ("pandrah sau", 1500),
    ("sava lakh", 125000),
    ("85000/-", 85000),
]

DIGITS = [
    ("char ek do teen, paanch chhe saat aath, nau zero ek do", "412356789012"),
    ("4 1 2 3 - 5 6 7 8 - 9 0 1 2", "412356789012"),
    ("UTR hai ji 4123 5678 9012", "412356789012"),
    ("double nine double eight 7 7 6 6 5 5 4 4", "998877665544"),
    ("nau aath saat chhah paanch chaar teen do ek shunya", "9876543210"),
    ("चार एक दो तीन पाँच छह सात आठ नौ शून्य एक दो", "412356789012"),
    ("41 23 56 78 90 12", "412356789012"),
    ("four one two three five six seven eight nine oh one two", "412356789012"),
    ("triple seven 1 2 3 4 5 6 7 8 9", "777123456789"),
]

UPIS = [
    ("ramesh point kumar at the rate ybl", "ramesh.kumar@ybl"),
    ("RAMESH.KUMAR@YBL", "ramesh.kumar@ybl"),
    ("uski id kyc dot update at the rate oksbi thi", "kyc.update@oksbi"),
    ("9876543210 at the rate paytm", "9876543210@paytm"),
    ("refund underscore help at the rate okaxis", "refund_help@okaxis"),
    ("amit123 at ybl", "amit123@ybl"),
]

TIMES = [
    ("lagbhag aadhe ghante pehle", 30),
    ("ek ghanta pehle", 60),
    ("paune ghante pehle", 45),
    ("15 min pehle", 15),
    ("10 minutes back", 10),
    ("dopahar 12 baje", 60),
    ("aaj subah 9:30 baje", 210),
    ("abhi abhi turant", 5),
]


def run():
    rows = []
    for text, exp in AMOUNTS:
        rows.append(("amount", text, exp, N.parse_amount(text, expecting_amount=True)))
    for text, exp in DIGITS:
        rows.append(("digits", text, exp, N.all_digits(text)))
    for text, exp in UPIS:
        rows.append(("upi", text, exp, X.extract_upi(text)))
    for text, exp in TIMES:
        rows.append(("time", text, exp, X.parse_minutes_ago(text, NOW)))
    ok = sum(1 for r in rows if r[2] == r[3])
    lines = [f"# Held-out stress set: {ok}/{len(rows)} correct ({100 * ok / len(rows):.0f}%)", "",
             "| Type | Caller said | Expected | Got | |", "|---|---|---|---|---|"]
    for kind, text, exp, got in rows:
        lines.append(f"| {kind} | {text} | {exp} | {got} | {'✅' if exp == got else '❌'} |")
    return ok, len(rows), "\n".join(lines)


if __name__ == "__main__":
    ok, n, md = run()
    from pathlib import Path
    Path(__file__).with_name("stress_report.md").write_text(md + "\n", encoding="utf-8")
    print(md)
