"""Evon fallback: used only when rules fail, and only accepted if the validators pass."""
from datetime import datetime

from saathi.dialog import Dialog

NOW = datetime(2026, 11, 6, 13, 0)


class FakeEvon:
    name = "fake-evon"

    def __init__(self, answers):
        self.answers = answers
        self.calls = []

    def extract_slot(self, slot, utterance, lang="hi"):
        self.calls.append(slot)
        return self.answers.get(slot)


def test_llm_fills_amount_rules_missed():
    llm = FakeEvon({"amount": {"value": 45000}})
    d = Dialog(now_fn=lambda: NOW, llm=llm)
    d.greeting()
    r = d.step("woh jo mere salary ka aadha tha, utna gaya")   # rules can't read this
    r = d.step("utna hi jitna salary ka aadha hota hai")       # answer to the amount question
    assert d.case.transactions[0].amount == 45000
    assert d.case.field_sources["amount"] == "llm"
    assert any(e["type"] == "llm_fallback" for e in r.events)


def test_llm_invented_utr_is_rejected():
    llm = FakeEvon({"utr": {"value": "412356789012"}})       # digits never said by the caller
    d = Dialog(now_fn=lambda: NOW, llm=llm)
    d.greeting()
    for u in ["45 hazaar gaye", "20 minute pehle", "UPI"]:
        d.step(u)
    d.step("SMS mein dekh raha hoon, ek minute")
    assert d.case.transactions[0].utr is None and "utr" not in d.case.field_sources


def test_llm_bad_upi_rejected_good_mobile_accepted():
    llm = FakeEvon({"suspect": {"upi": "not a upi", "mobile": "99999 00001", "account": None}})
    d = Dialog(now_fn=lambda: NOW, llm=llm)
    d.greeting()
    for u in ["45 hazaar gaye", "20 minute pehle", "UPI", "pata nahi"]:
        d.step(u)
    d.step("jo number se call aaya tha wahi")
    s = d.case.suspect
    assert s.upi is None and s.mobile == "9999900001" and s.status == "pending_confirm"


def test_rules_first_llm_not_called_when_rules_work():
    llm = FakeEvon({})
    d = Dialog(now_fn=lambda: NOW, llm=llm)
    d.greeting()
    d.step("45 hazaar gaye")
    assert llm.calls == []
