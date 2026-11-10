"""Synthetic demo complaints, produced by running real calls through the dialog engine.

Every name, number, UPI ID and UTR below is invented. Three of the calls pay the
same fraudster UPI ID, so the console shows a mule-ring alert.
"""
from __future__ import annotations

from typing import List

from .store import Store

RING_UPI = "kycupdate.help at the rate ybl"

SCRIPTS = [
    # (label, utterances)
    ("Synthetic: retired teacher, Patiala", [
        "CBI wale video call pe hain, bol rahe hain mere naam pe parcel mein drugs mile, abhi bhi video call chal raha hai",
        "do lakh rupaye bhej diye",
        "aadha ghanta pehle",
        "net banking se",
        "chaar ek do teen paanch chhe saat aath nau shunya ek do",
        "haan",
        "account number 5 0 1 0 0 2 3 4 5 6 7 8 9 hai",
        "haan",
        "punjab national bank",
        "nahi",
        "haan sahi hai",
    ]),
    ("Synthetic: shop owner, Ludhiana", [
        "bank wala bankar call aaya, KYC update ke liye OTP manga, maine bata diya",
        "nahi, call kat gaya",
        "45 hazaar",
        "20 minute pehle",
        "phonepe se",
        "7 7 1 2 0 4 5 5 3 9 0 1",
        "haan sahi",
        RING_UPI,
        "haan",
        "SBI",
        "nahi",
        "haan",
    ]),
    ("Synthetic: college student, Chandigarh", [
        "job ke registration fee ke naam pe paise liye",
        "saade teen hazaar",
        "dedh ghanta pehle",
        "gpay se",
        "pata nahi",
        RING_UPI,
        "haan",
        "HDFC",
        "nahi",
        "haan",
    ]),
    ("Synthetic: homemaker, Amritsar", [
        "KYC ke naam pe call aaya aur link bheja, anydesk download karwaya",
        "dedh lakh",
        "das minute pehle",
        "net banking",
        "3 3 0 9 8 1 2 2 7 6 5 4",
        "haan",
        RING_UPI,
        "haan",
        "ICICI",
        "haan",
        "25 hazaar aur gaye",
        "paanch minute pehle",
        "3 3 0 9 8 1 2 2 7 6 9 9",
        "haan",
        "nahi",
        "haan",
    ]),
    ("Synthetic: driver, Bathinda", [
        "OLX pe QR code scan karwaya, paise receive karne ke bahane",
        "12 hazaar",
        "kal raat",
        "9 0 0 1 2 3 4 5 6 7 8 8",
        "haan",
        "uska number 99999 00001 hai",
        "haan",
        "punjab and sind bank",
        "nahi",
        "haan",
    ]),
]


def run_script(store: Store, label: str, lines: List[str]) -> str:
    d = store.new_call()
    d.case.caller_label = label
    d.greeting()
    for line in lines:
        r = d.step(line)
        if r.done:
            break
    if d.state != "done":
        # the demo should always end with a filed case; file whatever was captured
        d._file()
    return d.case.id


def seed_cases(store: Store) -> List[str]:
    return [run_script(store, label, lines) for label, lines in SCRIPTS]
