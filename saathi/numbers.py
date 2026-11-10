"""Hinglish / Hindi / English spoken-number understanding.

Panicked callers say money and reference numbers in many ways:

    "45000", "45,000", "₹45k", "45 hazaar", "pachpan hazaar",
    "saade teen hazaar" (3,500), "dedh lakh" (1,50,000), "sava do lakh" (2,25,000),
    "do lakh pachas hazaar" (2,50,000), "forty five thousand", "पचास हज़ार"

and read digits as

    "4123 5678 9012", "chaar ek do teen ...", "double five", "nine eight seven"

This module turns all of these into plain integers / digit strings, without any
external dependency, so the downstream validators (UTR = 12 digits, mobile = 10
digits, ...) can check them and the dialog can read them back for confirmation.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Word tables
# ---------------------------------------------------------------------------

_ROMAN_HINDI = {
    0: "shunya shoonya sunya sifar zero",
    1: "ek eik one",
    2: "do two",
    3: "teen tin three",
    4: "char chaar four",
    5: "paanch panch paach five",
    6: "chhah chhe che chah chheh chhai six",
    7: "saat sat seven",
    8: "aath ath eight",
    9: "nau nao nine",
    10: "das dus ten",
    11: "gyarah gyaarah gyara eleven",
    12: "barah baarah bara twelve",
    13: "terah tera thirteen",
    14: "chaudah chauda fourteen",
    15: "pandrah pandra fifteen",
    16: "solah sola sixteen",
    17: "satrah satra seventeen",
    18: "atharah athara attharah eighteen",
    19: "unnis unees unnees nineteen",
    20: "bees twenty",
    21: "ikkis ikkees",
    22: "baais bais baees",
    23: "teis teyees teiis",
    24: "chaubis chaubees chobis",
    25: "pachchis pachees pacchis pachis",
    26: "chhabbis chhabbees chabbis",
    27: "sattais sattaees sattaes",
    28: "atthais athais atthaees",
    29: "untees untis",
    30: "tees thirty",
    31: "ikattis iktees ikatees",
    32: "battis battees",
    33: "taintis taintees tetis",
    34: "chautis chauntees chontis",
    35: "paintis paintees pentis",
    36: "chhattis chattees chhattees",
    37: "saintis saintees",
    38: "adtis artees artis adtees",
    39: "untalis untaalis",
    40: "chalis chaalis chalees forty",
    41: "iktalis iktaalis",
    42: "bayalis bayaalis",
    43: "taintalis taintaalis tetalis",
    44: "chavalis chauvalis chawalis",
    45: "paintalis paintaalis pentalis",
    46: "chhiyalis chiyalis",
    47: "saintalis saitalis",
    48: "adtalis artalis adtaalis",
    49: "unchas unchaas",
    50: "pachas pachaas fifty",
    51: "ikyavan ikyaavan ekyavan",
    52: "bavan baavan",
    53: "tirpan tirepan",
    54: "chauvan chauwan",
    55: "pachpan",
    56: "chhappan chappan",
    57: "sattavan sataavan",
    58: "atthavan athaavan",
    59: "unsath unsaath",
    60: "saath sixty",
    61: "iksath eksath",
    62: "basath baasath",
    63: "tirsath tresath",
    64: "chausath chaunsath",
    65: "painsath pensath",
    66: "chhiyasath chiyasath",
    67: "sadsath sarsath",
    68: "adsath arsath",
    69: "unhattar",
    70: "sattar seventy",
    71: "ikhattar ikahattar",
    72: "bahattar",
    73: "tihattar",
    74: "chauhattar",
    75: "pachhattar pachattar",
    76: "chhihattar",
    77: "sathattar sathhattar",
    78: "athhattar athattar",
    79: "unasi unyasi",
    80: "assi eighty",
    81: "ikyasi",
    82: "bayasi",
    83: "tirasi",
    84: "chaurasi",
    85: "pachasi",
    86: "chhiyasi",
    87: "sattasi",
    88: "athasi atthasi",
    89: "nawasi navasi",
    90: "nabbe ninety",
    91: "ikyanve",
    92: "banve baanve",
    93: "tiranve",
    94: "chauranve",
    95: "pachanve",
    96: "chhiyanve",
    97: "sattanve",
    98: "atthanve",
    99: "ninyanve ninnyanve",
}

_DEVANAGARI = {
    0: "शून्य ज़ीरो जीरो",
    1: "एक",
    2: "दो",
    3: "तीन",
    4: "चार",
    5: "पाँच पांच",
    6: "छह छः छे",
    7: "सात",
    8: "आठ",
    9: "नौ",
    10: "दस",
    11: "ग्यारह",
    12: "बारह",
    13: "तेरह",
    14: "चौदह",
    15: "पंद्रह पन्द्रह",
    16: "सोलह",
    17: "सत्रह",
    18: "अठारह",
    19: "उन्नीस",
    20: "बीस",
    25: "पच्चीस",
    30: "तीस",
    35: "पैंतीस",
    40: "चालीस",
    45: "पैंतालीस",
    50: "पचास",
    55: "पचपन",
    60: "साठ",
    65: "पैंसठ",
    70: "सत्तर",
    75: "पचहत्तर",
    80: "अस्सी",
    85: "पचासी",
    90: "नब्बे",
    95: "पचानवे",
}

# Punjabi: romanised + Gurmukhi
_PUNJABI = {
    0: "sifar ਸਿਫ਼ਰ ਸਿਫਰ ਜ਼ੀਰੋ", 1: "ikk ik ਇੱਕ ਇਕ", 2: "ਦੋ", 3: "tinn ਤਿੰਨ", 4: "ਚਾਰ", 5: "panj ਪੰਜ",
    6: "ਛੇ", 7: "satt ਸੱਤ", 8: "atth ਅੱਠ", 9: "naun ਨੌਂ ਨੌ", 10: "ਦਸ", 11: "giaran ਗਿਆਰਾਂ", 12: "baaran ਬਾਰਾਂ",
    15: "pandran ਪੰਦਰਾਂ", 20: "veeh vih ਵੀਹ", 21: "ikki ਇੱਕੀ", 22: "bai ਬਾਈ", 25: "pachchi ਪੱਚੀ",
    30: "tih ਤੀਹ", 35: "paintee ਪੈਂਤੀ", 40: "chaali ਚਾਲੀ", 45: "pantaali ਪੰਤਾਲੀ", 50: "panjah ਪੰਜਾਹ",
    55: "pachvanja ਪਚਵੰਜਾ", 60: "sath ਸੱਠ", 70: "ਸੱਤਰ", 75: "pachattar ਪਚੱਤਰ", 80: "ਅੱਸੀ", 90: "ਨੱਬੇ",
}
# Tamil: romanised (spoken) + Tamil script. Tens have combining forms: "naarpathi anju" = 45
_TAMIL = {
    0: "poojyam sunyam பூஜ்யம் சைபர்", 1: "onnu ondru oru ஒன்று ஒன்னு ஒரு", 2: "rendu irandu இரண்டு ரெண்டு",
    3: "moonu moondru மூன்று மூணு", 4: "naalu naangu நான்கு நாலு", 5: "anju aindhu ஐந்து அஞ்சு",
    6: "aaru ஆறு", 7: "ezhu yezhu ஏழு", 8: "ettu எட்டு", 9: "ombodhu onbadhu ஒன்பது", 10: "pathu பத்து",
    11: "pathinonnu பதினொன்று", 12: "pannendu பன்னிரண்டு", 15: "pathinanju பதினைந்து",
    20: "irupathu irupathi இருபது", 30: "muppathu muppathi முப்பது", 40: "naarpathu naarpathi நாற்பது",
    50: "aimbathu aimbathi ஐம்பது", 60: "arubathu arubathi அறுபது", 70: "ezhupathu ezhupathi எழுபது",
    80: "enbathu enbathi எண்பது", 90: "thonnooru thonnootri தொண்ணூறு",
    200: "irunooru இருநூறு", 300: "munnooru முன்னூறு", 400: "naanooru நானூறு", 500: "ainnooru ஐநூறு",
    600: "arunooru அறுநூறு", 700: "ezhunooru எழுநூறு", 800: "ennooru எண்ணூறு", 900: "thollaayiram தொள்ளாயிரம்",
}
_COMBINING_TENS = {"irupathi", "muppathi", "naarpathi", "aimbathi", "arubathi", "ezhupathi", "enbathi",
                   "thonnootri", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"}

WORD_TO_NUM: dict = {}
for _n, _words in (list(_ROMAN_HINDI.items()) + list(_DEVANAGARI.items()) + list(_PUNJABI.items())
                   + list(_TAMIL.items())):
    for _w in _words.split():
        WORD_TO_NUM.setdefault(_w, _n)

# English tens that combine with a following unit ("forty five" -> 45)
_EN_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
            "seventy": 70, "eighty": 80, "ninety": 90}
_EN_UNITS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
             "seven": 7, "eight": 8, "nine": 9}

# Words that are numbers but also very common Hindi/English words. They only
# count as numbers in a number context (next to a scale word or while we are
# explicitly collecting digits).
AMBIGUOUS_WORDS = {"do", "tin", "sat", "saath", "das", "bees", "nao", "char", "one",
                   "ath", "che", "bara", "tera", "sola", "tees", "bais", "dus"}

SCALES = {
    "sau": 100, "hundred": 100, "सौ": 100,
    "hazaar": 1_000, "hazar": 1_000, "hajar": 1_000, "hajaar": 1_000, "hazzar": 1_000,
    "thousand": 1_000, "k": 1_000, "हज़ार": 1_000, "हजार": 1_000,
    "lakh": 100_000, "lac": 100_000, "lakhs": 100_000, "lacs": 100_000, "laakh": 100_000,
    "lakh.": 100_000, "लाख": 100_000,
    "crore": 10_000_000, "crores": 10_000_000, "karod": 10_000_000, "karor": 10_000_000,
    "cr": 10_000_000, "करोड़": 10_000_000, "करोड": 10_000_000,
    # Punjabi (Gurmukhi)
    "ਸੌ": 100, "ਹਜ਼ਾਰ": 1_000, "ਹਜਾਰ": 1_000, "ਲੱਖ": 100_000, "ਲਖ": 100_000, "ਕਰੋੜ": 10_000_000,
    # Tamil
    "nooru": 100, "aayiram": 1_000, "ayiram": 1_000, "aayirathu": 1_000, "latcham": 100_000,
    "laksham": 100_000, "latsam": 100_000, "kodi": 10_000_000,
    "நூறு": 100, "ஆயிரம்": 1_000, "லட்சம்": 100_000, "கோடி": 10_000_000,
}
# Tamil glues the multiplier onto aayiram: "anjaayiram" = 5 x 1000
_TAMIL_AYIRAM = {"rend": "rendu", "irand": "rendu", "moov": "moonu", "moon": "moonu", "naal": "naalu",
                 "naan": "naalu", "anj": "anju", "ainth": "anju", "aar": "aaru", "ezh": "ezhu", "ett": "ettu",
                 "onbadh": "ombodhu", "ombadh": "ombodhu", "path": "pathu"}

# Fraction prefixes: saade teen = 3.5, sava do = 2.25, paune do = 1.75
FRACTION_PREFIX = {
    "saade": 0.5, "sade": 0.5, "saadhe": 0.5, "sadhe": 0.5, "saarhe": 0.5,
    "साढ़े": 0.5, "साढे": 0.5, "ਸਾਢੇ": 0.5, "ਸਵਾ": 0.25, "ਪੌਣੇ": -0.25,
    "sava": 0.25, "sawa": 0.25, "सवा": 0.25,
    "paune": -0.25, "pone": -0.25, "पौने": -0.25,
}
# Standalone fractional numbers
FRACTION_WORDS = {
    "dedh": 1.5, "derh": 1.5, "डेढ़": 1.5, "डेढ": 1.5,
    "dhai": 2.5, "dhaai": 2.5, "adhai": 2.5, "ढाई": 2.5,
    "aadha": 0.5, "adha": 0.5, "aadhe": 0.5, "adhe": 0.5, "आधा": 0.5, "आधे": 0.5, "half": 0.5,
    "ਡੇਢ": 1.5, "ਢਾਈ": 2.5, "ਅੱਧਾ": 0.5, "ਅੱਧੇ": 0.5, "arai": 0.5, "அரை": 0.5,
}

CURRENCY_CUES = {"rupaye", "rupaiye", "rupay", "rupees", "rupee", "rs", "rs.", "inr", "₹",
                 "रुपये", "रुपए", "रुपया", "rupya", "rupiya", "paise", "paisa", "पैसे",
                 "ਰੁਪਏ", "ਪੈਸੇ", "rubaai", "roobai", "ரூபாய்", "பணம்", "panam"}
CONNECTORS = {"aur", "and", "or", "और"}

MULTIPLIER_WORDS = {"double": 2, "triple": 3, "डबल": 2, "ट्रिपल": 3}

_DEV_DIGITS = str.maketrans("०१२३४५६७८९੦੧੨੩੪੫੬੭੮੯௦௧௨௩௪௫௬௭௮௯", "0123456789" * 3)
_PUNCT_SPLIT = re.compile(r"[\s,;:!?\"'()\[\]{}|/\\]+|(?<!\d)\.(?!\d)|।")
_NUM_ALPHA_SPLIT = re.compile(r"(\d+(?:\.\d+)?)")


def normalize(text: str) -> str:
    """Lowercase, convert Devanagari digits, drop thousands separators."""
    s = text.translate(_DEV_DIGITS).lower()
    s = s.replace("₹", " ₹ ")
    s = re.sub(r"(?<=\d),(?=\d)", "", s)  # 1,20,000 -> 120000
    s = s.replace("–", " ").replace("—", " ").replace("-", " ")
    return s


def tokenize(text: str) -> List[str]:
    """Split into tokens; also split glued number+word tokens ("45k" -> 45, k)."""
    out: List[str] = []
    for raw in _PUNCT_SPLIT.split(normalize(text)):
        if not raw:
            continue
        for part in _NUM_ALPHA_SPLIT.split(raw):
            part = part.strip(".")
            if not part:
                continue
            m = re.fullmatch(r"([a-z]+?)a{1,2}yiram", part)
            if m and m.group(1) in _TAMIL_AYIRAM:          # "anjaayiram" -> 5 aayiram
                out += [_TAMIL_AYIRAM[m.group(1)], "aayiram"]
                continue
            out.append(part)
    return out


def _is_numeric(tok: str) -> bool:
    return bool(re.fullmatch(r"\d+(?:\.\d+)?", tok))


# ---------------------------------------------------------------------------
# Amounts
# ---------------------------------------------------------------------------

@dataclass
class AmountCandidate:
    value: int
    has_scale: bool
    has_currency: bool
    start: int
    end: int
    text: str


def _word_value(tok: str, allow_ambiguous: bool) -> Optional[float]:
    if _is_numeric(tok):
        return float(tok)
    if tok in FRACTION_WORDS:
        return FRACTION_WORDS[tok]
    if tok in WORD_TO_NUM:
        if tok in AMBIGUOUS_WORDS and not allow_ambiguous:
            return None
        return float(WORD_TO_NUM[tok])
    return None


def find_amounts(text: str, expecting_amount: bool = False) -> List[AmountCandidate]:
    """Find every money-like expression in an utterance."""
    toks = tokenize(text)
    cands: List[AmountCandidate] = []
    i = 0
    n = len(toks)
    while i < n:
        start = i
        total = 0.0
        cur = 0.0
        has_num = has_scale = has_currency = False
        pending_frac = 0.0
        j = i
        # currency symbol/word before the number ("rs 4500", "₹ 4500")
        if toks[j] in CURRENCY_CUES and j + 1 < n:
            has_currency = True
            j += 1
        while j < n:
            t = toks[j]
            nxt = toks[j + 1] if j + 1 < n else ""
            if t in FRACTION_PREFIX:
                pending_frac = FRACTION_PREFIX[t]
                j += 1
                continue
            allow_amb = expecting_amount or nxt in SCALES or bool(pending_frac)
            v = _word_value(t, allow_amb)
            if v is not None:
                # combining tens: English "forty five", Tamil "naarpathi anju"
                if t in _COMBINING_TENS and nxt in WORD_TO_NUM and 0 < WORD_TO_NUM[nxt] < 10:
                    v += WORD_TO_NUM[nxt]
                    j += 1
                if pending_frac:
                    v += pending_frac
                    pending_frac = 0.0
                # two plain digit-numbers in a row without scale = not one amount
                if has_num and cur and not has_scale and _is_numeric(t):
                    break
                cur += v
                has_num = True
                j += 1
                continue
            if t in SCALES and (has_num or pending_frac):
                if pending_frac and not cur:      # "sava lakh" = 1.25 lakh, "paune lakh" = 0.75 lakh
                    cur = 1 + pending_frac
                    pending_frac = 0.0
                    has_num = True
                mult = SCALES[t]
                if mult == 100:
                    cur = (cur or 1) * 100
                else:
                    total += (cur or 1) * mult
                    cur = 0.0
                has_scale = True
                j += 1
                continue
            if t in CONNECTORS and has_num and nxt and (_word_value(nxt, True) is not None or nxt in FRACTION_PREFIX):
                j += 1
                continue
            if t in CURRENCY_CUES and has_num:
                has_currency = True
                j += 1
            break
        if has_num:
            value = total + cur
            digits_only = all(_is_numeric(x) for x in toks[start:j] if x not in CURRENCY_CUES)
            raw_len = len(re.sub(r"\D", "", "".join(toks[start:j])))
            # long bare digit runs are reference numbers, not money
            if not (digits_only and not has_scale and raw_len >= 9):
                if 0 < value < 1e10:
                    cands.append(AmountCandidate(int(round(value)), has_scale, has_currency,
                                                 start, j, " ".join(toks[start:j])))
            i = max(j, i + 1)
        else:
            i += 1
    return cands


def parse_amount(text: str, expecting_amount: bool = False) -> Optional[int]:
    """Best single amount in the utterance, or None."""
    cands = find_amounts(text, expecting_amount)
    if not cands:
        return None
    strong = [c for c in cands if c.has_scale or c.has_currency]
    pool = strong or (cands if expecting_amount else [])
    if not pool:
        return None
    # prefer the last strong mention (people correct themselves: "nahi nahi, 46 hazaar")
    return pool[-1].value


# ---------------------------------------------------------------------------
# Digit strings (UTR, phone, account numbers)
# ---------------------------------------------------------------------------

DIGIT_FILLERS = {"hai", "h", "he", "tha", "the", "is", "number", "no.", "num", "utr",
                 "reference", "ref", "id", "mera", "meri", "uska", "uski", "ka", "ki", "ke",
                 "wala", "vala", "hain", "aur", "then", "phir", "fir", "ok", "okay",
                 "haan", "ha", "ji", "जी", "है", "का", "की", "नंबर", "बोल", "raha", "rha",
                 "hoon", "hu", "um", "uh", "matlab", "yaani", "dash", "space", "comma"}


def spoken_digit_runs(text: str) -> List[str]:
    """Return runs of digits spoken or written in the utterance, longest first order kept.

    Fillers ("hai", "number", "ji") don't break a run; any other word does.
    """
    toks = tokenize(text)
    runs: List[str] = []
    cur = ""
    i = 0
    n = len(toks)
    while i < n:
        t = toks[i]
        nxt = toks[i + 1] if i + 1 < n else ""
        if t in MULTIPLIER_WORDS and nxt:
            v = _word_value(nxt, True)
            if v is not None and float(v).is_integer():
                cur += str(int(v)) * MULTIPLIER_WORDS[t]
                i += 2
                continue
        if re.fullmatch(r"\d+", t):
            cur += t
            i += 1
            continue
        if t == "no" and cur and nxt and (_word_value(nxt, True) is not None):
            cur += "9"  # "no" read as nau between digits
            i += 1
            continue
        if t in ("oh", "o") and cur and nxt and (_word_value(nxt, True) is not None or nxt.isdigit()):
            cur += "0"  # English "oh" for zero inside a number
            i += 1
            continue
        v = _word_value(t, True) if t not in FRACTION_WORDS else None
        if v is not None and float(v).is_integer():
            iv = int(v)
            if t in _COMBINING_TENS and nxt in WORD_TO_NUM and 0 < WORD_TO_NUM[nxt] < 10:
                iv += WORD_TO_NUM[nxt]
                i += 1
            cur += str(iv)
            i += 1
            continue
        if t in DIGIT_FILLERS:
            i += 1
            continue
        if cur:
            runs.append(cur)
            cur = ""
        i += 1
    if cur:
        runs.append(cur)
    return runs


def longest_digit_run(text: str) -> str:
    runs = spoken_digit_runs(text)
    return max(runs, key=len) if runs else ""


def all_digits(text: str) -> str:
    """All spoken/written digits concatenated (used while collecting one long number)."""
    return "".join(spoken_digit_runs(text))


# ---------------------------------------------------------------------------
# Speaking numbers back (for read-back confirmation through TTS)
# ---------------------------------------------------------------------------

_DIGIT_WORDS = {
    "hi": ["शून्य", "एक", "दो", "तीन", "चार", "पाँच", "छह", "सात", "आठ", "नौ"],
    "en": ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"],
    "pa": ["ਸਿਫ਼ਰ", "ਇੱਕ", "ਦੋ", "ਤਿੰਨ", "ਚਾਰ", "ਪੰਜ", "ਛੇ", "ਸੱਤ", "ਅੱਠ", "ਨੌਂ"],
    "ta": ["பூஜ்யம்", "ஒன்று", "இரண்டு", "மூன்று", "நான்கு", "ஐந்து", "ஆறு", "ஏழு", "எட்டு", "ஒன்பது"],
}
_SCALE_WORDS = {
    "hi": ("करोड़", "लाख", "हज़ार", "सौ", "रुपये"),
    "pa": ("ਕਰੋੜ", "ਲੱਖ", "ਹਜ਼ਾਰ", "ਸੌ", "ਰੁਪਏ"),
    "ta": ("கோடி", "லட்சம்", "ஆயிரம்", "நூறு", "ரூபாய்"),
}


def speak_digits(digits: str, lang: str = "hi", group: int = 4) -> str:
    """'412356789012' -> 'चार एक दो तीन, पाँच छह सात आठ, ...' grouped for clarity."""
    words = _DIGIT_WORDS.get(lang, _DIGIT_WORDS["hi"])
    chunks = [digits[i:i + group] for i in range(0, len(digits), group)]
    return ", ".join(" ".join(words[int(c)] if c.isdigit() else c for c in chunk) for chunk in chunks)


def format_inr(amount: int) -> str:
    """Indian digit grouping: 1234567 -> '12,34,567'."""
    s = str(int(amount))
    if len(s) <= 3:
        return s
    head, tail = s[:-3], s[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return ",".join(parts + [tail])


def speak_amount(amount: int, lang: str = "hi") -> str:
    """Natural spoken form: 145000 -> 'एक लाख पैंतालीस हज़ार रुपये'."""
    if lang not in _SCALE_WORDS:
        return f"{format_inr(amount)} rupees"
    w_crore, w_lakh, w_hazaar, w_sau, w_rs = _SCALE_WORDS[lang]
    parts = []
    crore, rem = divmod(int(amount), 10_000_000)
    lakh, rem = divmod(rem, 100_000)
    hazaar, rem = divmod(rem, 1_000)
    sau, rem = divmod(rem, 100)
    for val, word in ((crore, w_crore), (lakh, w_lakh), (hazaar, w_hazaar), (sau, w_sau)):
        if val:
            parts.append(f"{val} {word}")
    if rem:
        parts.append(str(rem))
    return " ".join(parts) + " " + w_rs


def iter_number_words() -> Iterable[Tuple[str, int]]:
    return WORD_TO_NUM.items()
