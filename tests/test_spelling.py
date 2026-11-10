"""UPI names from Indic-script transcripts are read back letter by letter and can be spelled."""
from datetime import datetime

from saathi import extract as X
from saathi import translit as T
from saathi.dialog import Dialog

NOW = datetime(2026, 11, 6, 13, 0)


def to_suspect(d):
    for u in ["45 hazaar gaye", "20 minute pehle", "UPI", "pata nahi"]:
        d.step(u)


def test_phonetic_name_triggers_letter_readback_and_spelling():
    d = Dialog(now_fn=lambda: NOW, lang="pa")
    d.greeting()
    to_suspect(d)
    r = d.step("ਗੁਰਪ੍ਰੀਤ ਐਟ ਦ ਰੇਟ ਪੇਟੀਐਮ")
    assert d.case.suspect.spell_check and "ਅੱਖਰਾਂ" in r.text          # letters read back, not the word
    d.step("ਨਹੀਂ")
    assert d.state == "suspect_spell"
    r = d.step("ਜੀ, ਯੂ, ਆਰ, ਪੀ, ਆਰ, ਈ, ਈ, ਟੀ")
    assert d.case.suspect.upi == "gurpreet@paytm" and d.case.suspect.spelled_by_caller
    d.step("ਹਾਂ ਜੀ")
    assert d.case.suspect.status == "confirmed"


def test_latin_or_spelled_upi_does_not_need_spelling():
    assert not X.upi_needs_spelling("ramesh dot kumar at the rate ybl")
    assert not X.upi_needs_spelling("आर के एट द रेट पेटीएम")
    assert X.upi_needs_spelling("सपोर्ट एट द रेट पेटीएम")


def test_spell_out_and_parse_roundtrip():
    for lang in ("hi", "pa", "ta", "en"):
        spoken = T.spell_out("refund.help2", lang)
        assert T.spelled_word(spoken.replace(",", " ").split()) == "refund.help2", lang
