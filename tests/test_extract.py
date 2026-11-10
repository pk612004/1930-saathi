from datetime import datetime

import pytest

from saathi import extract as X
from saathi import validators as V

NOW = datetime(2026, 11, 6, 13, 0)


@pytest.mark.parametrize("text,expected", [
    ("ramesh dot kumar at the rate ybl", "ramesh.kumar@ybl"),
    ("paise ramesh.k@ybl pe gaye", "ramesh.k@ybl"),
    ("nine eight seven six five four three two one zero at the rate paytm", "9876543210@paytm"),
    ("uska upi refund dot desk at the rate okaxis hai", "refund.desk@okaxis"),
])
def test_upi(text, expected):
    assert X.extract_upi(text) == expected


def test_suspect_mobile_and_account():
    assert X.extract_suspect("jisko bheje uska number 98765 43210 hai").mobile == "9876543210"
    assert X.extract_suspect("account number 50100234567891 hai").account == "50100234567891"


@pytest.mark.parametrize("text,minutes", [
    ("20 minute pehle", 20), ("aadha ghanta pehle", 30), ("dedh ghanta pehle", 90),
    ("abhi abhi", 5), ("do ghante pehle", 120), ("subah 11 baje", 120), ("12:30 baje", 30),
    ("kal raat", 18 * 60), ("about 40 minutes ago", 40),
])
def test_minutes_ago(text, minutes):
    assert X.parse_minutes_ago(text, NOW) == minutes


def test_fraud_classification():
    assert X.classify_fraud("CBI wale video call pe hai, parcel mein drugs bola")[0] == "digital_arrest"
    assert X.classify_fraud("bank wala bankar call aaya, OTP bataya")[0] == "bank_kyc_vishing"
    assert X.classify_fraud("OLX pe QR code scan karwaya")[0] == "upi_qr_collect"
    assert X.classify_fraud("telegram pe task diya, like karne ke paise")[0] == "investment_task"
    assert X.classify_fraud("kuch samajh nahi aaya")[0] == "other"


def test_live_threat():
    assert X.detect_live_threat("abhi bhi video call chal raha hai").live
    t = X.detect_live_threat("anydesk download karwaya")
    assert t.live and t.remote_app
    assert not X.detect_live_threat("call kat gaya, ab koi baat nahi").live


def test_yes_no_dont_know():
    assert X.yes_no("haan sahi hai") is True
    assert X.yes_no("nahi galat hai") is False
    assert X.yes_no("pata nahi") is None
    assert X.is_dont_know("UTR yaad nahi")
    assert X.is_repeat("dobara boliye")


def test_bank_and_mode():
    assert X.detect_bank("mera SBI mein account hai") == "State Bank of India"
    assert X.detect_bank("bank of india") == "Bank of India"
    assert X.detect_bank("punjab and sind bank") == "Punjab & Sind Bank"
    assert X.detect_payment_mode("phonepe se bheje") == "UPI"
    assert X.detect_payment_mode("net banking se") == "Net banking / IMPS / NEFT"


def test_language():
    assert X.detect_language("KYC ke naam pe call aaya aur link bheja") == "hi"
    assert X.detect_language("I searched customer care number on Google for a refund") == "en"
    assert X.detect_language("मेरे पैसे कट गए") == "hi"


def test_validators():
    assert V.check_utr("412356789012").ok
    assert not V.check_utr("41235678901").ok
    assert V.check_mobile("+91 98765 43210").value == "9876543210"
    assert not V.check_mobile("12345").ok
    assert V.check_upi("ramesh@ybl").confidence == 1.0
    assert V.check_upi("ramesh@weirdbank").confidence < 1.0
    assert V.check_ifsc("SBIN0001234").ok
    assert V.mask("412356789012") == "********9012"


@pytest.mark.parametrize("text,expected", [
    ("रमेश डॉट कुमार एट द रेट वाई बी एल", "ramesh.kumar@ybl"),
    ("आर के एट द रेट पेटीएम", "rk@paytm"),
    ("रमेश एक दो तीन एट द रेट ओके एक्सिस", "ramesh123@okaxis"),
    ("प्रिया डॉट शर्मा एट द रेट ओकेएसबीआई", "priya.sharma@oksbi"),
    ("उसका यूपीआई हेल्प डॉट डेस्क एट द रेट आईबीएल है", "help.desk@ibl"),
    ("के वाई सी डॉट हेल्प एट द रेट वाईबीएल", "kyc.help@ybl"),
    ("रमेश@ybl", "ramesh@ybl"),
    ("सुनीता एट द रेट ओके एचडीएफसी बैंक", "sunita@okhdfcbank"),
])
def test_upi_from_devanagari_transcript(text, expected):
    """Prisma writes Hindi audio in Devanagari; UPI IDs must come back in Latin."""
    assert X.extract_upi(text) == expected


def test_utr_not_glued_to_amount_from_prisma():
    """Real Prisma v3 output (check_gnani.py, 10 Nov 2026): amount and UTR in one sentence."""
    for t in ["मेरे ₹45,000 कट गए, यू टी आर है 412356789012",
              "मेरे 45,000 रुपये कट गए यूटीआर है 412356789012।"]:
        ex = X.extract_all(t, expecting="utr")
        assert ex.utr == "412356789012" and ex.amount == 45000
    assert X.extract_all("4123 5678 9012", expecting="utr").utr == "412356789012"
    assert X.extract_all("7 7 1 2 0 4 5 5 3 9 0", expecting="utr").utr_partial == "77120455390"
