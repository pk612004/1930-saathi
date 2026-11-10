"""Punjabi (Gurmukhi) and Tamil calls, as Prisma might transcribe them."""
from datetime import datetime

import pytest

from saathi import extract as X
from saathi import numbers as N
from saathi.dialog import Dialog

NOW = datetime(2026, 11, 6, 13, 0)


def run(lines):
    d = Dialog(now_fn=lambda: NOW)
    d.greeting()
    out = [d.step(l) for l in lines]
    return d, out


def test_punjabi_gurmukhi_call():
    d, r = run([
        "ਬੈਂਕ ਵਾਲਾ ਬਣਕੇ ਕਾਲ ਆਈ, ਕੇਵਾਈਸੀ ਲਈ ਓਟੀਪੀ ਮੰਗਿਆ",
        "ਨਹੀਂ",
        "ਪੰਤਾਲੀ ਹਜ਼ਾਰ",
        "ਵੀਹ ਮਿੰਟ ਪਹਿਲਾਂ",
        "ਯੂਪੀਆਈ",
        "ਚਾਰ ਇੱਕ ਦੋ ਤਿੰਨ ਪੰਜ ਛੇ ਸੱਤ ਅੱਠ ਨੌਂ ਸਿਫ਼ਰ ਇੱਕ ਦੋ",
        "ਹਾਂ ਜੀ",
        "ਰਮੇਸ਼ ਐਟ ਦ ਰੇਟ ਵਾਈ ਬੀ ਐਲ",
        "ਹਾਂ",
        "ਪੰਜਾਬ ਨੈਸ਼ਨਲ ਬੈਂਕ",
        "ਨਹੀਂ",
        "ਹਾਂ ਜੀ ਸਹੀ ਹੈ",
    ])
    c = d.case
    assert c.lang == "pa" and c.status == "filed", [t.text for t in c.transcript]
    t = c.transactions[0]
    assert (t.amount, t.minutes_ago, t.utr, t.utr_status) == (45000, 20, "412356789012", "confirmed")
    assert c.suspect.upi == "ramesh@ybl" and c.victim_bank == "Punjab National Bank"
    assert r[0].text.startswith("ਇੱਕ ਜ਼ਰੂਰੀ")           # Punjabi threat check
    assert "ਯੂਟੀਆਰ" in r[-2].text                        # Punjabi summary read-back


def test_tamil_call():
    d, r = run([
        "பேங்க்ல இருந்து கால் பண்ணாங்க, கேஒய்சி அப்டேட்னு ஓடிபி கேட்டாங்க",
        "இல்லை",
        "நாற்பது ஆயிரம்",
        "20 நிமிஷம் முன்னாடி",
        "ஜிபே",
        "நான்கு ஒன்று இரண்டு மூன்று ஐந்து ஆறு ஏழு எட்டு ஒன்பது பூஜ்யம் ஒன்று இரண்டு",
        "ஆமா",
        "ரமேஷ் அட் த ரேட் ஓகேஆக்சிஸ்",
        "ஆமா",
        "இந்தியன் ஓவர்சீஸ் பேங்க்",
        "இல்லை",
        "ஆமா சரி",
    ])
    c = d.case
    assert c.lang == "ta" and c.status == "filed", [t.text for t in c.transcript]
    t = c.transactions[0]
    assert (t.amount, t.minutes_ago, t.utr) == (40000, 20, "412356789012")
    assert c.suspect.upi == "ramesh@okaxis" and c.victim_bank == "Indian Overseas Bank"
    assert "யுடிஆர்" in r[-2].text


@pytest.mark.parametrize("text,expected", [
    ("ਪੰਤਾਲੀ ਹਜ਼ਾਰ", 45000), ("ਸਾਢੇ ਤਿੰਨ ਹਜ਼ਾਰ", 3500), ("pantaali hazaar", 45000),
    ("naarpathi anjaayiram", 45000), ("rendu latcham", 200000), ("45 ஆயிரம்", 45000), ("௪௫௦௦௦", 45000),
    ("irupathi rendu aayiram ainnooru", 22500),
])
def test_amounts_other_languages(text, expected):
    assert N.parse_amount(text, expecting_amount=True) == expected


def test_language_detection():
    assert X.detect_language("ਮੇਰੇ ਪੈਸੇ ਕੱਟੇ ਗਏ") == "pa"
    assert X.detect_language("என் பணம் போச்சு") == "ta"
    assert X.detect_language("naan panam anuppunen, ippo enna pannanum") == "ta"
    assert X.detect_language("mainu call aaya si, ohne paise kadd lae, tuhada bank") == "pa"


def test_tamil_time_units():
    assert X.parse_minutes_ago("rendu mani neram munnadi", NOW) == 120
    assert X.parse_minutes_ago("11 manikku", NOW) == 120
