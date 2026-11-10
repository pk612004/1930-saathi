"""Turn Devanagari transcripts of UPI IDs back into Latin.

Prisma transcribes Hindi audio in Devanagari, so a caller saying
"ramesh dot kumar at the rate ybl" may come back as
"रमेश डॉट कुमार एट द रेट वाई बी एल". UPI IDs are Latin, so we need:

* spelled English letters  (वाई बी एल -> ybl, आर के -> rk)
* known payment-handle spellings (पेटीएम -> paytm, ओके एक्सिस -> okaxis)
* a phonetic transliteration for names (रमेश -> ramesh, शर्मा -> sharma)
* fuzzy matching of the handle against the list of real UPI handles

The read-back step then lets the caller confirm or correct the result.
"""
from __future__ import annotations

import difflib
import re
from typing import List, Optional

DEVANAGARI = re.compile("[\u0900-\u097F\u0A00-\u0A7F\u0B80-\u0BFF]")

# English letter names as Hindi speakers say them
LETTER_NAMES = {
    "ए": "a", "ऐ": "a", "बी": "b", "सी": "c", "डी": "d", "ई": "e", "एफ": "f", "जी": "g", "एच": "h",
    "आई": "i", "जे": "j", "के": "k", "एल": "l", "एम": "m", "एन": "n", "ओ": "o", "पी": "p",
    "क्यू": "q", "आर": "r", "एस": "s", "टी": "t", "यू": "u", "वी": "v", "डब्ल्यू": "w", "डब्लू": "w",
    "एक्स": "x", "वाई": "y", "ज़ेड": "z", "जेड": "z",
}

# Gurmukhi / Tamil letter names, after mapping to Devanagari code points, plus common variants
LETTER_NAMES.update({
    "ऐफ": "f", "ऐच": "h", "ऐल": "l", "ऐम": "m", "ऐन": "n", "ऐस": "s", "ऐक्स": "x", "किऊ": "q", "डबलयू": "w",
    "पि": "p", "पी": "p", "टि": "t", "डि": "d", "सि": "c", "वि": "v", "जि": "g", "ऎल्": "l", "ऎम्": "m",
    "ऎन्": "n", "ऎस्": "s", "ऎफ्": "f", "ऎक्स्": "x", "आर्": "r", "वै": "y", "ऎ": "a",
})

# How the common UPI handles come out in Devanagari (with and without spaces)
PSP_DEVANAGARI = {
    "वाईबीएल": "ybl", "आईबीएल": "ibl", "एक्सल": "axl", "एएक्सएल": "axl", "पेटीएम": "paytm",
    "ओकेएक्सिस": "okaxis", "ओकेऐक्सिस": "okaxis", "ओकेएसबीआई": "oksbi", "ओकेएचडीएफसीबैंक": "okhdfcbank",
    "ओकेआईसीआईसीआई": "okicici", "यूपीआई": "upi", "आईसीआईसीआई": "icici", "एसबीआई": "sbi",
    "एचडीएफसीबैंक": "hdfcbank", "एक्सिसबैंक": "axisbank", "कोटक": "kotak", "एयरटेल": "airtel",
    "जियो": "jio", "फ्रीचार्ज": "freecharge", "यसबैंक": "yesbank", "एपीएल": "apl",
}

_CONS = {
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "n", "च": "ch", "छ": "chh", "ज": "j", "झ": "jh",
    "ञ": "n", "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n", "त": "t", "थ": "th", "द": "d",
    "ध": "dh", "न": "n", "प": "p", "फ": "f", "ब": "b", "भ": "bh", "म": "m", "य": "y", "र": "r",
    "ल": "l", "व": "v", "श": "sh", "ष": "sh", "स": "s", "ह": "h", "क़": "q", "ख़": "kh", "ग़": "g",
    "ज़": "z", "ड़": "d", "ढ़": "rh", "फ़": "f", "ऴ": "zh", "ऱ": "r", "ऩ": "n",
}
_NUKTA = {"क": "q", "ख": "kh", "ग": "g", "ज": "z", "ड": "d", "ढ": "rh", "फ": "f", "स": "sh", "ल": "l"}
_VOWELS = {"अ": "a", "आ": "a", "इ": "i", "ई": "i", "उ": "u", "ऊ": "u", "ऋ": "ri", "ए": "e", "ऐ": "ai",
           "ओ": "o", "औ": "au", "ऑ": "o", "ऎ": "e", "ऒ": "o"}
_MATRAS = {"ा": "a", "ि": "i", "ी": "i", "ु": "u", "ू": "u", "ृ": "ri", "े": "e", "ै": "ai", "ो": "o",
           "ौ": "au", "ॉ": "o", "ॅ": "e", "ॆ": "e", "ॊ": "o"}
_VIRAMA, _NUKTA_SIGN = "्", "़"
_NASAL = {"ं": "n", "ँ": "n", "ः": "h"}


# Gurmukhi (U+0A00) and Tamil (U+0B80) are laid out like Devanagari (U+0900), so most letters map by
# a fixed offset. Script-specific signs are handled first.
_GURMUKHI_SPECIAL = {"\u0A71": "", "\u0A70": "\u0902"}          # addak (gemination) dropped, tippi -> anusvara


def to_devanagari(word: str) -> str:
    out = []
    for ch in word:
        cp = ord(ch)
        if ch in _GURMUKHI_SPECIAL:
            out.append(_GURMUKHI_SPECIAL[ch])
        elif 0x0A00 <= cp <= 0x0A7F:
            out.append(chr(cp - 0x100))
        elif 0x0B80 <= cp <= 0x0BFF:
            out.append(chr(cp - 0x280))
        else:
            out.append(ch)
    return "".join(out)


def transliterate(word: str) -> str:
    """Phonetic Indic -> Latin with final-schwa deletion (रमेश -> ramesh, ਸ਼ਰਮਾ -> sharma, ரமேஷ் -> ramesh)."""
    word = to_devanagari(word)
    out: List[str] = []
    i, n = 0, len(word)
    pending_a = False
    while i < n:
        ch = word[i]
        nxt = word[i + 1] if i + 1 < n else ""
        if ch in _CONS or (ch in _NUKTA and nxt == _NUKTA_SIGN):
            if pending_a:
                out.append("a")
            if nxt == _NUKTA_SIGN:
                out.append(_NUKTA.get(ch, _CONS.get(ch, "")))
                i += 1
                nxt = word[i + 1] if i + 1 < n else ""
            else:
                out.append(_CONS[ch])
            if nxt == _VIRAMA:
                pending_a = False
                i += 2
                continue
            if nxt in _MATRAS:
                out.append(_MATRAS[nxt])
                pending_a = False
                i += 2
                continue
            pending_a = True
            i += 1
            continue
        if pending_a:
            out.append("a")
            pending_a = False
        if ch in _VOWELS:
            out.append(_VOWELS[ch])
        elif ch in _NASAL:
            out.append(_NASAL[ch])
        elif ch.isascii():
            out.append(ch)
        i += 1
    # final inherent 'a' is dropped (schwa deletion): रमेश -> ramesh, not ramesha
    return "".join(out)


def is_devanagari(tok: str) -> bool:
    return bool(DEVANAGARI.search(tok))


# How English letters are said in each script (used both to SPEAK spellings and to PARSE them)
SPELL_NAMES = {
    "hi": "ए बी सी डी ई एफ जी एच आई जे के एल एम एन ओ पी क्यू आर एस टी यू वी डब्ल्यू एक्स वाई ज़ेड".split(),
    "pa": "ਏ ਬੀ ਸੀ ਡੀ ਈ ਐਫ ਜੀ ਐਚ ਆਈ ਜੇ ਕੇ ਐਲ ਐਮ ਐਨ ਓ ਪੀ ਕਿਊ ਆਰ ਐਸ ਟੀ ਯੂ ਵੀ ਡਬਲਯੂ ਐਕਸ ਵਾਈ ਜ਼ੈੱਡ".split(),
    "ta": "ஏ பி சி டி ஈ எஃப் ஜி ஹெச் ஐ ஜே கே எல் எம் என் ஓ பீ க்யூ ஆர் எஸ் டீ யூ வி டபிள்யூ எக்ஸ் வை ஜெட்".split(),
    "en": [chr(c) for c in range(ord("a"), ord("z") + 1)],
}
_RAW_LETTERS = {}
for _lang, _names in SPELL_NAMES.items():
    for _i, _n in enumerate(_names):
        _RAW_LETTERS.setdefault(_n, chr(ord("a") + _i))
_RAW_LETTERS.update({"பி": "p", "டி": "d"})   # common Tamil variants


def spell_out(word: str, lang: str) -> str:
    """'refund' -> 'आर, ई, एफ, यू, एन, डी' in the caller's script."""
    names = SPELL_NAMES.get(lang if lang in SPELL_NAMES else "hi")
    out = []
    for ch in word:
        if "a" <= ch <= "z":
            out.append(names[ord(ch) - ord("a")])
        elif ch.isdigit():
            out.append(ch)
        elif ch == ".":
            out.append({"hi": "डॉट", "pa": "ਡਾਟ", "ta": "டாட்", "en": "dot"}.get(lang, "dot"))
        elif ch == "_":
            out.append("underscore")
    return ", ".join(out)


def letters_from_names(tokens: List[str]) -> Optional[str]:
    """'आर के' -> 'rk' only if *every* token is an English letter name."""
    if not tokens:
        return None
    out = []
    for t in tokens:
        if t in _RAW_LETTERS:
            out.append(_RAW_LETTERS[t])
        elif to_devanagari(t) in LETTER_NAMES:
            out.append(LETTER_NAMES[to_devanagari(t)])
        else:
            return None
    return "".join(out)


def is_letter_name(tok: str) -> bool:
    return tok in _RAW_LETTERS and not tok.isascii() or to_devanagari(tok) in LETTER_NAMES


def spelled_word(tokens: List[str]) -> Optional[str]:
    """Parse a letter-by-letter spelling: 'आर ई एफ यू एन डी' / 'r e f u n d' / with digits and dots."""
    from .numbers import WORD_TO_NUM
    out = []
    for t in tokens:
        t = t.strip(",")
        if not t:
            continue
        if t in ("डॉट", "ਡਾਟ", "டாட்", "dot", "."):
            out.append(".")
        elif t in ("underscore", "अंडरस्कोर"):
            out.append("_")
        elif t.isdigit():
            out.append(t)
        elif len(t) == 1 and t.isascii() and t.isalpha():
            out.append(t.lower())
        elif t in _RAW_LETTERS or to_devanagari(t) in LETTER_NAMES:
            out.append(_RAW_LETTERS.get(t) or LETTER_NAMES[to_devanagari(t)])
        elif t in WORD_TO_NUM and WORD_TO_NUM[t] < 10:
            out.append(str(WORD_TO_NUM[t]))
        else:
            continue  # fillers like "जैसे", "फिर"
    word = "".join(out).strip("._")
    return word if len(word) >= 2 else None


# Tamil / Gurmukhi spellings of handles (raw script)
PSP_OTHER = {"வைபிஎல்": "ybl", "பேடிஎம்": "paytm", "ஓகேஆக்சிஸ்": "okaxis", "ஓகேஎஸ்பிஐ": "oksbi",
             "ஐபிஎல்": "ibl", "யுபிஐ": "upi", "ਵਾਈਬੀਐਲ": "ybl", "ਪੇਟੀਐਮ": "paytm", "ਓਕੇਐਕਸਿਸ": "okaxis",
             "ਓਕੇਐਸਬੀਆਈ": "oksbi", "ਯੂਪੀਆਈ": "upi"}


def segment_letters(token: str) -> Optional[str]:
    """Split a glued run of spelled letters: 'ਆਈਬੀਐਲ' -> 'ibl', 'वाईबीएल' -> 'ybl' (greedy longest match)."""
    names = sorted(set(_RAW_LETTERS) | set(LETTER_NAMES), key=len, reverse=True)
    i, out = 0, []
    while i < len(token):
        for n in names:
            if token.startswith(n, i):
                out.append(_RAW_LETTERS.get(n) or LETTER_NAMES[n])
                i += len(n)
                break
        else:
            return None
    return "".join(out) if len(out) >= 2 else None


def resolve_handle(tokens: List[str], known) -> Optional[str]:
    """Best UPI handle from the token(s) after '@'."""
    if not tokens:
        return None
    raw_joined = "".join(tokens)
    if raw_joined in PSP_OTHER:
        return PSP_OTHER[raw_joined]
    seg = segment_letters(raw_joined)
    if seg and seg in known:
        return seg
    if raw_joined.startswith(("ओके", "ਓਕੇ", "ஓகே")):
        rest = segment_letters(raw_joined[2:])
        if rest and "ok" + rest in known:
            return "ok" + rest
    tokens = [to_devanagari(t) for t in tokens]
    joined_dev = "".join(tokens)
    cands = []
    if joined_dev in PSP_DEVANAGARI:
        cands.append(PSP_DEVANAGARI[joined_dev])
    lt = letters_from_names(tokens)
    if lt:
        cands.append(lt)
    # "ओके एक्सिस" -> "ok" + transliterated rest
    latin = []
    for t in tokens:
        if t in PSP_DEVANAGARI:
            latin.append(PSP_DEVANAGARI[t])
        elif t in LETTER_NAMES and len(tokens) > 1:
            latin.append(LETTER_NAMES[t])
        elif t == "ओके":
            latin.append("ok")
        elif is_devanagari(t):
            latin.append(transliterate(t))
        else:
            latin.append(re.sub(r"[^a-z]", "", t))
    cands.append("".join(latin))
    cands.append(re.sub(r"[^a-z]", "", tokens[0]) if not is_devanagari(tokens[0]) else transliterate(tokens[0]))
    for c in cands:
        if c in known:
            return c
    for c in cands:
        m = difflib.get_close_matches(c, list(known), n=1, cutoff=0.75)
        if m:
            return m[0]
    best = next((c for c in cands if c), None)
    return best
