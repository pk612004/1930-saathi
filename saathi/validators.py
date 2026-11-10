"""Format validators for the identifiers a 1930 complaint needs.

Every value the voice agent captures is checked here *in code* before it is
accepted, so a speech-recognition slip ("11 digits instead of 12") becomes a
targeted re-prompt instead of a wrong complaint.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

# Common UPI handles (payment service provider suffixes). Unknown handles are
# still accepted, but with lower confidence.
KNOWN_UPI_HANDLES = {
    "ybl", "ibl", "axl", "okaxis", "oksbi", "okhdfcbank", "okicici", "paytm", "ptyes",
    "ptaxis", "pthdfc", "ptsbi", "upi", "apl", "yapl", "icici", "sbi", "hdfcbank",
    "axisbank", "kotak", "kmbl", "yesbank", "yesbankltd", "freecharge", "airtel",
    "jio", "fbl", "federal", "idfcbank", "indus", "pnb", "barodampay", "boi",
    "cnrb", "unionbank", "waaxis", "wahdfcbank", "wasbi", "waicici", "rbl", "aubank",
    "ikwik", "postbank", "abfspay", "superyes", "naviaxis", "slc", "mbk",
}


@dataclass
class Check:
    ok: bool
    value: Optional[str]
    reason: str = ""
    confidence: float = 1.0


def check_utr(digits_or_text: str) -> Check:
    """UPI / IMPS reference numbers (RRN) are 12 digits; NEFT/RTGS UTRs are 16/22 chars."""
    raw = re.sub(r"\s", "", digits_or_text or "").upper()
    if re.fullmatch(r"\d{12}", raw):
        return Check(True, raw, "12-digit UPI/IMPS reference")
    if re.fullmatch(r"[A-Z]{4}[A-Z0-9]{12}", raw) or re.fullmatch(r"[A-Z]{4}[A-Z0-9]{18}", raw):
        return Check(True, raw, "NEFT/RTGS UTR")
    digits = re.sub(r"\D", "", raw)
    if digits:
        return Check(False, digits, f"got {len(digits)} digits, expected 12")
    return Check(False, None, "no reference number heard")


def check_mobile(digits: str) -> Check:
    d = re.sub(r"\D", "", digits or "")
    if len(d) == 12 and d.startswith("91"):
        d = d[2:]
    elif len(d) == 11 and d.startswith("0"):
        d = d[1:]
    if re.fullmatch(r"[6-9]\d{9}", d):
        return Check(True, d, "Indian mobile number")
    if d:
        return Check(False, d, f"got {len(d)} digits, expected a 10-digit mobile number")
    return Check(False, None, "no number heard")


def check_account(digits: str) -> Check:
    d = re.sub(r"\D", "", digits or "")
    if 9 <= len(d) <= 18:
        return Check(True, d, "bank account number", 0.8)
    if d:
        return Check(False, d, f"got {len(d)} digits, account numbers have 9-18")
    return Check(False, None, "no account number heard")


def check_ifsc(text: str) -> Check:
    t = re.sub(r"\s", "", (text or "")).upper()
    if re.fullmatch(r"[A-Z]{4}0[A-Z0-9]{6}", t):
        return Check(True, t, "IFSC")
    return Check(False, t or None, "IFSC is 4 letters, 0, then 6 characters")


def check_upi(vpa: str) -> Check:
    v = (vpa or "").strip().lower()
    m = re.fullmatch(r"([a-z0-9._-]{2,256})@([a-z]{2,64})", v)
    if not m:
        return Check(False, v or None, "UPI ID looks like name@bank")
    handle = m.group(2)
    if handle in KNOWN_UPI_HANDLES:
        return Check(True, v, f"known UPI handle @{handle}")
    return Check(True, v, f"unrecognised handle @{handle}", 0.6)


def check_amount(amount: Optional[int]) -> Check:
    if amount is None:
        return Check(False, None, "no amount heard")
    if amount < 1:
        return Check(False, str(amount), "amount must be positive")
    if amount > 100_000_000:
        return Check(False, str(amount), "amount above 10 crore, please confirm", 0.3)
    return Check(True, str(amount), "amount")


def mask(value: Optional[str], keep: int = 4) -> str:
    """Mask identifiers for SMS/logs: 412356789012 -> ********9012."""
    if not value:
        return ""
    if "@" in value:
        name, handle = value.split("@", 1)
        return (name[:2] + "*" * max(len(name) - 2, 1)) + "@" + handle
    return "*" * max(len(value) - keep, 0) + value[-keep:]
