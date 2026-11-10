import pytest

from saathi import numbers as N


@pytest.mark.parametrize("text,expected", [
    ("mere 45000 rupaye kat gaye", 45000),
    ("₹45k", 45000),
    ("45 hazaar gaye", 45000),
    ("pachpan hazaar", 55000),
    ("saade teen hazaar", 3500),
    ("dedh lakh", 150000),
    ("dhai lakh", 250000),
    ("sava do lakh", 225000),
    ("paune do lakh", 175000),
    ("do lakh pachas hazaar", 250000),
    ("ek lakh bees hazaar paanch sau", 120500),
    ("forty five thousand", 45000),
    ("पचास हज़ार रुपये", 50000),
    ("1,20,000 rupees", 120000),
    ("4.5 lakh", 450000),
    ("teen sau pachas rupaye", 350),
    ("nahi nahi 46 hazaar the", 46000),
    ("2 crore", 20000000),
])
def test_amounts(text, expected):
    assert N.parse_amount(text, expecting_amount=True) == expected


def test_reference_number_is_not_an_amount():
    assert N.parse_amount("UTR 412356789012 hai") is None
    assert N.parse_amount("UTR 412356789012 hai", expecting_amount=True) is None


def test_ambiguous_word_needs_context():
    # "do" means "give"/"two"; without a scale word it is not money unless we asked for an amount
    assert N.parse_amount("mujhe do baar call aaya") is None


@pytest.mark.parametrize("text,expected", [
    ("4123 5678 9012", ["412356789012"]),
    ("chaar ek do teen paanch chhe saat aath nau shunya ek do", ["412356789012"]),
    ("double five teen nine eight", ["55398"]),
    ("nine eight seven six five four three two one zero", ["9876543210"]),
    ("UTR hai 4123 aur 5678 9012", ["412356789012"]),
    ("चार एक दो तीन", ["4123"]),
    ("triple seven 2", ["7772"]),
])
def test_digit_runs(text, expected):
    assert N.spoken_digit_runs(text) == expected


def test_speak_back():
    assert N.speak_digits("412356789012") == "चार एक दो तीन, पाँच छह सात आठ, नौ शून्य एक दो"
    assert N.speak_digits("4123", "en") == "four one two three"
    assert N.format_inr(1234567) == "12,34,567"
    assert N.speak_amount(145000) == "1 लाख 45 हज़ार रुपये"
