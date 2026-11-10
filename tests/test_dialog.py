from datetime import datetime

from saathi.dialog import Dialog

NOW = datetime(2026, 11, 6, 13, 0)


def run(lines, lang=None):
    d = Dialog(now_fn=lambda: NOW, lang=lang)
    d.greeting()
    replies = []
    for line in lines:
        replies.append(d.step(line))
    return d, replies


def test_happy_path_hinglish():
    d, r = run([
        "Bank wala bankar call aaya, KYC update bola, maine OTP bataya aur 45 hazaar kat gaye",
        "nahi, call kat gaya",
        "bees minute pehle",
        "phonepe se",
        "chaar ek do teen paanch chhe saat aath nau shunya ek do",
        "haan sahi hai",
        "ramesh dot kumar at the rate ybl",
        "haan",
        "SBI mein",
        "nahi",
        "haan sab sahi hai",
    ])
    c = d.case
    assert r[-1].done and c.status == "filed"
    t = c.transactions[0]
    assert (t.amount, t.minutes_ago, t.utr, t.utr_status, t.mode) == (45000, 20, "412356789012", "confirmed", "UPI")
    assert c.suspect.upi == "ramesh.kumar@ybl" and c.suspect.status == "confirmed"
    assert c.victim_bank == "State Bank of India"
    assert c.fraud_type == "bank_kyc_vishing"


def test_amount_volunteered_is_not_asked_again():
    d, r = run(["UPI se 45 hazaar kat gaye bees minute pehle"])
    # amount, time and mode were all in the first sentence -> next question is the UTR
    assert d.state == "utr"


def test_live_threat_interrupt_comes_first():
    d, r = run(["CBI wale video call pe hain, abhi bhi video call chal raha hai, do lakh bhej diye"])
    assert d.case.live_threat
    assert r[0].text.startswith("सबसे पहले")
    assert any(e["type"] == "live_threat" for e in r[0].events)


def test_validator_reprompts_short_utr():
    d, r = run(["45 hazaar gaye", "20 minute pehle", "UPI", "7 7 1 2 0 4 5 5 3 9 0"])
    assert "11" in r[-1].text and d.state == "utr"
    assert any(e["type"] == "validator_reprompt" for e in r[-1].events)
    r2 = d.step("7 7 1 2, 0 4 5 5, 3 9 0 1")
    assert d.state == "utr_confirm" and d.case.transactions[0].utr == "771204553901"


def test_readback_inline_correction():
    d, r = run(["45 hazaar gaye", "20 minute pehle", "UPI", "4 1 2 3 5 6 7 8 9 0 1 2",
                "nahi, 4 1 2 3 5 6 7 8 9 0 1 3", "haan"])
    t = d.case.transactions[0]
    assert t.utr == "412356789013" and t.utr_status == "confirmed"
    assert t.utr_first_heard == "412356789012"


def test_dont_know_utr_moves_on():
    d, r = run(["45 hazaar gaye", "20 minute pehle", "UPI", "pata nahi"])
    assert d.case.transactions[0].utr_status == "unknown"
    assert d.state == "suspect"


def test_two_failures_never_trap_the_caller():
    d, r = run(["45 hazaar gaye", "20 minute pehle", "UPI", "hmm", "hmm", "hmm"])
    assert d.case.transactions[0].utr_status == "unknown"
    assert d.state == "suspect"


def test_summary_correction_with_value():
    d, r = run(["45 hazaar gaye", "20 minute pehle", "UPI", "pata nahi", "ramesh at the rate ybl", "haan",
                "SBI", "nahi", "nahi, rakam 46 hazaar thi"])
    assert d.case.transactions[0].amount == 46000
    assert d.state == "summary"


def test_multiple_transactions():
    d, r = run(["dedh lakh gaye", "das minute pehle", "net banking", "3 3 0 9 8 1 2 2 7 6 5 4", "haan",
                "kyc dot help at the rate ybl", "haan", "ICICI", "haan", "25 hazaar aur gaye",
                "paanch minute pehle", "3 3 0 9 8 1 2 2 7 6 9 9", "haan", "nahi", "haan"])
    c = d.case
    assert c.status == "filed"
    assert [t.amount for t in c.transactions] == [150000, 25000]
    assert c.total_amount == 175000


def test_english_call():
    d, r = run(["Someone from customer care took my money", "forty five thousand rupees", "about 40 minutes ago",
                "UPI", "4 1 2 3 5 6 7 8 9 0 1 2", "yes", "refund dot desk at the rate okaxis", "yes", "HDFC",
                "no", "yes"])
    assert d.case.lang == "en" and d.case.status == "filed"
    assert r[0].text.startswith("How much")


def test_repeat_request():
    d, r = run(["45 hazaar gaye"])
    last = r[-1].text
    r2 = d.step("dobara boliye")
    assert r2.text == last
