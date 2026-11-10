"""Synthetic 1930 calls with ground truth, plus a scripted caller that answers the agent.

Everything is invented: amounts, UTRs, UPI IDs and phone numbers are random.
The caller speaks each value in one of several realistic styles (digits,
Hindi number words, English words, grouped digits, "double five", ...), so the
evaluation measures how robust the understanding layer is to how people talk.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import List, Optional

from saathi import numbers as N

PSP = ["ybl", "okaxis", "oksbi", "okhdfcbank", "paytm", "ibl", "axl", "okicici"]
NAMES = ["ramesh", "sunita", "kycupdate", "refund", "rk", "help", "support", "amit", "priya", "rewards", "verify"]
BANKS = [("State Bank of India", ["SBI", "state bank"]), ("HDFC Bank", ["HDFC"]), ("ICICI Bank", ["ICICI"]),
         ("Punjab National Bank", ["PNB", "punjab national bank"]), ("Axis Bank", ["axis bank"]),
         ("Bank of Baroda", ["bank of baroda"]), ("Canara Bank", ["canara bank"]), ("Kotak Mahindra Bank", ["kotak"]),
         ("Punjab & Sind Bank", ["punjab and sind bank"]), ("Union Bank of India", ["union bank"])]
MODES = [("UPI", ["phonepe se", "gpay se", "UPI se", "paytm se"]), ("Card", ["debit card se"]),
         ("Net banking / IMPS / NEFT", ["net banking se", "IMPS se"])]

STORIES = {
    "digital_arrest": ["CBI wale video call pe aaye, bole mere naam pe parcel mein drugs hai",
                       "police officer bankar call aaya, money laundering ka case bola"],
    "bank_kyc_vishing": ["bank wala bankar call aaya, KYC update ke liye OTP manga, maine bata diya",
                         "call aaya ki account band ho jayega, maine OTP de diya"],
    "upi_qr_collect": ["OLX pe QR code scan karwaya, paise receive karne ke bahane",
                       "collect request aayi aur maine pin dala"],
    "investment_task": ["telegram pe task diya, youtube video like karne ke paise, phir investment karwaya"],
    "job_fraud": ["naukri ke liye registration fee maangi, work from home job bola"],
    "fake_customer_care": ["google pe customer care number dhoonda refund ke liye, unhone paise katwa diye"],
    "remote_access": ["link bheja aur anydesk download karwaya, phir account se paise gaye"],
}
STORIES_EN = {
    "digital_arrest": ["someone claiming to be CBI said a parcel in my name had drugs"],
    "bank_kyc_vishing": ["a caller from the bank asked for KYC and I shared the OTP"],
    "upi_qr_collect": ["a buyer on OLX sent a QR code to receive money and I scanned it"],
    "investment_task": ["I was given tasks on telegram and then asked to invest for high returns"],
    "job_fraud": ["they asked for a registration fee for a work from home job"],
    "fake_customer_care": ["I searched customer care number on Google for a refund and they took my money"],
    "remote_access": ["they made me install anydesk and took money from my account"],
}
LIVE = ["abhi bhi video call chal raha hai", "wo abhi bhi call pe hai aur aur paise maang raha hai"]
LIVE_EN = ["they are still on the video call with me"]

# --- other scripts: how Prisma may write the same call in Devanagari (hi-dev), Gurmukhi (pa), Tamil (ta)
SCRIPT_LANGS = ("dev", "pa", "ta")
STORIES_SCRIPT = {
    "dev": {
        "digital_arrest": "सीबीआई वाले वीडियो कॉल पर आए, बोले मेरे नाम पर पार्सल में ड्रग्स है",
        "bank_kyc_vishing": "बैंक वाला बनकर कॉल आया, केवाईसी के लिए ओटीपी माँगा, मैंने बता दिया",
        "upi_qr_collect": "ओएलएक्स पर क्यूआर कोड स्कैन करवाया, पैसे रिसीव करने के बहाने",
        "investment_task": "टेलीग्राम पर टास्क दिया, फिर निवेश करवाया",
        "job_fraud": "नौकरी के लिए रजिस्ट्रेशन फीस माँगी",
        "fake_customer_care": "रिफंड के लिए कस्टमर केयर नंबर ढूँढा, उन्होंने पैसे कटवा दिए",
        "remote_access": "लिंक भेजा और anydesk डाउनलोड करवाया",
    },
    "pa": {
        "digital_arrest": "ਸੀਬੀਆਈ ਵਾਲੇ ਵੀਡੀਓ ਕਾਲ ਉੱਤੇ ਆਏ, ਕਹਿੰਦੇ ਮੇਰੇ ਨਾਮ ਤੇ ਪਾਰਸਲ ਵਿੱਚ ਡਰੱਗਜ਼ ਹੈ",
        "bank_kyc_vishing": "ਬੈਂਕ ਵਾਲਾ ਬਣਕੇ ਕਾਲ ਆਈ, ਕੇਵਾਈਸੀ ਲਈ ਓਟੀਪੀ ਮੰਗਿਆ",
        "upi_qr_collect": "ਓਐਲਐਕਸ ਉੱਤੇ qr code ਸਕੈਨ ਕਰਵਾਇਆ",
        "investment_task": "ਟੈਲੀਗ੍ਰਾਮ ਉੱਤੇ task ਦਿੱਤਾ, ਫਿਰ investment ਕਰਵਾਈ",
        "job_fraud": "ਨੌਕਰੀ ਲਈ registration fee ਮੰਗੀ",
        "fake_customer_care": "refund ਲਈ customer care number ਲੱਭਿਆ, ਉਹਨਾਂ ਨੇ ਪੈਸੇ ਕਟਵਾ ਦਿੱਤੇ",
        "remote_access": "ਲਿੰਕ ਭੇਜਿਆ ਤੇ anydesk ਡਾਊਨਲੋਡ ਕਰਵਾਇਆ",
    },
    "ta": {
        "digital_arrest": "சிபிஐன்னு சொல்லி வீடியோ கால்ல வந்தாங்க, என் பெயர்ல பார்சல்ல டிரக்ஸ் இருக்குன்னாங்க",
        "bank_kyc_vishing": "பேங்க்ல இருந்து கால் பண்ணாங்க, கேஒய்சி அப்டேட்னு ஓடிபி கேட்டாங்க",
        "upi_qr_collect": "olx-ல qr code scan பண்ண சொன்னாங்க",
        "investment_task": "telegram-ல task குடுத்தாங்க, அப்புறம் investment பண்ண சொன்னாங்க",
        "job_fraud": "வேலைக்கு registration fee கேட்டாங்க",
        "fake_customer_care": "refund-க்கு customer care number தேடினேன், அவங்க பணம் எடுத்துட்டாங்க",
        "remote_access": "link அனுப்பி anydesk download பண்ண சொன்னாங்க",
    },
}
LIVE_SCRIPT = {"dev": "अभी भी वीडियो कॉल चल रहा है", "pa": "ਹਾਲੇ ਵੀ ਵੀਡੀਓ ਕਾਲ ਚੱਲ ਰਹੀ ਹੈ",
               "ta": "இன்னும் வீடியோ கால்ல இருக்காங்க"}
YES_S = {"dev": "हाँ", "pa": "ਹਾਂ ਜੀ", "ta": "ஆமா"}
NO_S = {"dev": "नहीं", "pa": "ਨਹੀਂ", "ta": "இல்லை"}
DK_S = {"dev": "पता नहीं", "pa": "ਪਤਾ ਨਹੀਂ", "ta": "தெரியல"}
THOUSAND = {"dev": "हज़ार", "pa": "ਹਜ਼ਾਰ", "ta": "ஆயிரம்"}
LAKH = {"dev": "लाख", "pa": "ਲੱਖ", "ta": "லட்சம்"}
RUPEES = {"dev": "रुपये", "pa": "ਰੁਪਏ", "ta": "ரூபாய்"}
MIN_AGO = {"dev": "{m} मिनट पहले", "pa": "{m} ਮਿੰਟ ਪਹਿਲਾਂ", "ta": "{m} நிமிஷம் முன்னாடி"}
AT_S = {"dev": "एट द रेट", "pa": "ਐਟ ਦ ਰੇਟ", "ta": "அட் த ரேட்"}
DOT_S = {"dev": "डॉट", "pa": "ਡਾਟ", "ta": "டாட்"}
# name -> spelling in each script. "refund"/"support" are included on purpose: phonetic
# transliteration cannot always recover English spellings, and the eval should show that.
NAME_S = {
    "ramesh": ("रमेश", "ਰਮੇਸ਼", "ரமேஷ்"), "sunita": ("सुनीता", "ਸੁਨੀਤਾ", "சுனிதா"), "amit": ("अमित", "ਅਮਿਤ", "அமித்"),
    "priya": ("प्रिया", "ਪ੍ਰਿਆ", "ப்ரியா"), "help": ("हेल्प", "ਹੈਲਪ", "ஹெல்ப்"), "rk": ("आर के", "ਆਰ ਕੇ", "ஆர் கே"),
    "refund": ("रिफंड", "ਰਿਫੰਡ", "ரீஃபண்ட்"), "support": ("सपोर्ट", "ਸਪੋਰਟ", "சப்போர்ட்"),
}
PSP_S = {"ybl": ("वाई बी एल", "ਵਾਈ ਬੀ ਐਲ", "வைபிஎல்"), "paytm": ("पेटीएम", "ਪੇਟੀਐਮ", "பேடிஎம்"),
         "okaxis": ("ओके एक्सिस", "ਓਕੇਐਕਸਿਸ", "ஓகேஆக்சிஸ்"), "oksbi": ("ओके एसबीआई", "ਓਕੇਐਸਬੀਆਈ", "ஓகேஎஸ்பிஐ"),
         "ibl": ("आईबीएल", "ਆਈਬੀਐਲ", "ஐபிஎல்")}
BANK_S = {"dev": [("State Bank of India", "एसबीआई"), ("HDFC Bank", "एचडीएफसी"), ("Punjab National Bank", "पंजाब नेशनल बैंक"),
                  ("Canara Bank", "केनरा बैंक")],
          "pa": [("State Bank of India", "ਐਸਬੀਆਈ"), ("Punjab National Bank", "ਪੰਜਾਬ ਨੈਸ਼ਨਲ ਬੈਂਕ"),
                 ("Punjab & Sind Bank", "ਪੰਜਾਬ ਐਂਡ ਸਿੰਧ ਬੈਂਕ"), ("HDFC Bank", "ਐਚਡੀਐਫਸੀ")],
          "ta": [("State Bank of India", "எஸ்பிஐ"), ("Indian Overseas Bank", "இந்தியன் ஓவர்சீஸ் பேங்க்"),
                 ("Canara Bank", "கனரா பேங்க்"), ("Indian Bank", "இந்தியன் பேங்க்")]}
MODE_S = {"dev": {"UPI": "फोनपे से", "Card": "कार्ड से", "Net banking / IMPS / NEFT": "नेट बैंकिंग से"},
          "pa": {"UPI": "ਯੂਪੀਆਈ", "Card": "ਕਾਰਡ", "Net banking / IMPS / NEFT": "ਨੈੱਟ ਬੈਂਕਿੰਗ"},
          "ta": {"UPI": "ஜிபே", "Card": "கார்டு", "Net banking / IMPS / NEFT": "நெட் பேங்கிங்"}}
FILLERS = {"hi": ["umm", "matlab", "haan to", "ji"], "en": ["umm", "so", "uh"], "dev": ["मतलब", "जी", "हाँ तो"],
           "pa": ["ਜੀ", "ਮਤਲਬ"], "ta": ["அது வந்து", "ம்ம்"]}
_SIDX = {"dev": 0, "pa": 1, "ta": 2}

_EN_DIG = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"]
_HI_DIG = ["shunya", "ek", "do", "teen", "chaar", "paanch", "chhe", "saat", "aath", "nau"]


def _hindi_word(n: int) -> Optional[str]:
    for w, v in N.WORD_TO_NUM.items():
        if v == n and w.isascii() and w not in N.AMBIGUOUS_WORDS and w not in _EN_DIG and w.isalpha() \
                and w not in ("twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety", "ten",
                              "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen",
                              "eighteen", "nineteen", "zero"):
            return w
    return None


@dataclass
class TxnTruth:
    amount: int
    minutes: int
    utr: Optional[str]
    mode: str


@dataclass
class CallTruth:
    lang: str
    fraud_type: str
    live_threat: bool
    txns: List[TxnTruth]
    suspect_kind: str
    suspect: str
    bank: str
    bank_cue: str
    mode_cue: str
    story: str
    style_seed: int = 0


def _amount(rng: random.Random) -> int:
    return rng.choice([3500, 4999, 12000, 25000, 45000, 55000, 99000, 150000, 175000, 200000, 250000,
                       320000, 7500, 18500, 65000])


def make_call(rng: random.Random, mix=None) -> CallTruth:
    mix = mix or {"hi": 0.40, "dev": 0.25, "en": 0.15, "pa": 0.10, "ta": 0.10}
    r, acc, lang = rng.random(), 0.0, "hi"
    for k, v in mix.items():
        acc += v
        if r < acc:
            lang = k
            break
    ftype = rng.choice(list(STORIES))
    # "live threat" = scam still in progress OR a remote-access app still installed (every remote_access story)
    live = ftype == "remote_access" or (ftype == "digital_arrest" and rng.random() < 0.6)
    n_txn = 2 if rng.random() < 0.15 else 1
    mode_name, mode_cues = rng.choice(MODES)
    txns = []
    for i in range(n_txn):
        utr = None if rng.random() < 0.1 else "".join(str(rng.randrange(10)) for _ in range(12))
        if utr and utr[0] == "0":
            utr = "1" + utr[1:]
        txns.append(TxnTruth(_amount(rng), rng.choice([5, 10, 15, 20, 30, 40, 45, 90, 120, 180]), utr, mode_name))
    kind = rng.choice(["upi", "upi", "upi", "mobile", "account"])
    if kind == "upi" and lang in SCRIPT_LANGS:
        name = rng.choice(list(NAME_S))
        if rng.random() < 0.3:
            name += "." + rng.choice([n for n in NAME_S if n != "rk"])
        suspect = f"{name}@{rng.choice(list(PSP_S))}"
    elif kind == "upi":
        name = rng.choice(NAMES)
        if rng.random() < 0.4:
            name += "." + rng.choice(NAMES)
        if rng.random() < 0.3:
            name += str(rng.randrange(10, 99))
        suspect = f"{name}@{rng.choice(PSP)}"
    elif kind == "mobile":
        suspect = str(rng.choice([6, 7, 8, 9])) + "".join(str(rng.randrange(10)) for _ in range(9))
    else:
        suspect = str(rng.randrange(1, 10)) + "".join(str(rng.randrange(10)) for _ in range(rng.choice([10, 11, 13])))
    if lang in SCRIPT_LANGS:
        bank, cue = rng.choice(BANK_S[lang])
        story = STORIES_SCRIPT[lang][ftype]
        return CallTruth(lang, ftype, live, txns, kind, suspect, bank, cue, MODE_S[lang][mode_name], story,
                         rng.randrange(1 << 30))
    bank, cues = rng.choice(BANKS)
    story = rng.choice((STORIES_EN if lang == "en" else STORIES)[ftype])
    return CallTruth(lang, ftype, live, txns, kind, suspect, bank, rng.choice(cues), rng.choice(mode_cues), story,
                     rng.randrange(1 << 30))


# --------------------------------------------------------------------------- rendering

def _script_amount(a: int, lang: str, rng: random.Random) -> str:
    opts = [f"{a} {RUPEES[lang]}"]
    if a % 1000 == 0 and a < 100000:
        opts.append(f"{a // 1000} {THOUSAND[lang]}")
    if a % 100000 == 0:
        opts.append(f"{a // 100000} {LAKH[lang]}")
    return rng.choice(opts)


def say_amount(a: int, lang: str, rng: random.Random) -> str:
    if lang in SCRIPT_LANGS:
        return _script_amount(a, lang, rng)
    styles = []
    if lang == "en":
        styles.append(f"{N.format_inr(a)} rupees")
        if a % 1000 == 0 and a < 100000:
            styles.append(f"{a // 1000} thousand")
        return rng.choice(styles)
    styles += [f"{a} rupaye", f"₹{N.format_inr(a)}"]
    if a % 1000 == 0 and a < 100000:
        styles.append(f"{a // 1000} hazaar")
        w = _hindi_word(a // 1000)
        if w:
            styles.append(f"{w} hazaar")
    if a % 1000 == 500 and a < 100000:
        w = _hindi_word(a // 1000)
        if w:
            styles.append(f"saade {w} hazaar")
    if a == 150000:
        styles.append("dedh lakh")
    if a == 250000:
        styles.append("dhai lakh")
    if a % 100000 == 0:
        styles.append(f"{a // 100000} lakh")
    if a == 175000:
        styles.append("paune do lakh")
    return rng.choice(styles)


def say_minutes(m: int, lang: str, rng: random.Random) -> str:
    if lang in SCRIPT_LANGS:
        return MIN_AGO[lang].format(m=m)
    if lang == "en":
        return rng.choice([f"about {m} minutes ago", f"{m} minutes ago"]) if m < 60 else f"{m // 60} hours ago" if m % 60 == 0 else f"{m} minutes ago"
    options = [f"{m} minute pehle"]
    if m == 30:
        options.append("aadha ghanta pehle")
    if m == 90:
        options.append("dedh ghanta pehle")
    if m == 120:
        options += ["do ghante pehle", "2 ghante pehle"]
    if m == 180:
        options.append("teen ghante pehle")
    if m == 5:
        options.append("abhi abhi")
    if m == 10:
        options.append("das minute pehle")
    return rng.choice(options)


def say_digits(d: str, lang: str, rng: random.Random) -> str:
    style = rng.choice(["plain", "grouped", "spaced", "words", "words"])
    if lang in SCRIPT_LANGS:
        if style in ("words",):
            words = N._DIGIT_WORDS["hi" if lang == "dev" else lang]
            return " ".join(words[int(c)] for c in d)
        return " ".join(d) if style == "spaced" else (" ".join(d[i:i + 4] for i in range(0, len(d), 4))
                                                       if style == "grouped" else d)
    if style == "plain":
        return d
    if style == "grouped":
        return " ".join(d[i:i + 4] for i in range(0, len(d), 4))
    if style == "spaced":
        return " ".join(d)
    words = _EN_DIG if lang == "en" else _HI_DIG
    out, i = [], 0
    while i < len(d):
        if i + 1 < len(d) and d[i] == d[i + 1] and rng.random() < 0.5:
            out += ["double", words[int(d[i])]]
            i += 2
        else:
            out.append(words[int(d[i])])
            i += 1
    return " ".join(out)


def say_suspect(t: CallTruth, rng: random.Random) -> str:
    if t.suspect_kind == "upi" and t.lang in SCRIPT_LANGS:
        i = _SIDX[t.lang]
        name, psp = t.suspect.split("@")
        parts = [NAME_S[n][i] for n in name.split(".")]
        return f" {DOT_S[t.lang]} ".join(parts) + f" {AT_S[t.lang]} " + PSP_S[psp][i]
    if t.suspect_kind != "upi" and t.lang in SCRIPT_LANGS:
        return " ".join(t.suspect) if t.suspect_kind == "account" else f"{t.suspect[:5]} {t.suspect[5:]}"
    if t.suspect_kind == "upi":
        name, psp = t.suspect.split("@")
        spoken = name.replace(".", " dot ")
        # spoken digits inside a handle
        spoken = "".join(f" {ch} " if ch.isdigit() else ch for ch in spoken)
        at = "at the rate"
        return " ".join(f"{spoken} {at} {psp}".split())
    if t.suspect_kind == "mobile":
        pre = "his number is " if t.lang == "en" else "uska number "
        d = t.suspect
        return pre + rng.choice([f"{d[:5]} {d[5:]}", say_digits(d, t.lang, rng)]) + ("" if t.lang == "en" else " hai")
    pre = "account number " if t.lang == "en" else "account number "
    return pre + " ".join(t.suspect)


def yes(lang):
    return YES_S.get(lang) or ("yes" if lang == "en" else "haan")


def no(lang):
    return NO_S.get(lang) or ("no" if lang == "en" else "nahi")


def dont_know(lang):
    return DK_S.get(lang) or ("don't know" if lang == "en" else "pata nahi")


def disfluent(text: str, lang: str, rng: random.Random, p_filler=0.3, p_stutter=0.12) -> str:
    """Real callers say 'umm', and stutter: 'chaar chaar ek do' (which adds a digit!)."""
    toks = text.split(" ")
    if rng.random() < p_stutter:
        idx = [i for i, t in enumerate(toks) if t in N.WORD_TO_NUM and N.WORD_TO_NUM[t] < 10]
        if idx:
            i = rng.choice(idx)
            toks.insert(i, toks[i])
    out = " ".join(toks)
    if rng.random() < p_filler:
        out = rng.choice(FILLERS.get(lang, FILLERS["hi"])) + " " + out
    return out


@dataclass
class CallerSim:
    """Answers whatever the agent asks, using the ground truth."""
    truth: CallTruth
    rng: random.Random
    txn_i: int = 0
    log: List[str] = field(default_factory=list)

    @property
    def t(self) -> TxnTruth:
        return self.truth.txns[min(self.txn_i, len(self.truth.txns) - 1)]

    def answer(self, state: str, dialog) -> str:
        T, L, rng = self.truth, self.truth.lang, self.rng
        case = dialog.case
        if state == "open":
            parts = [T.story]
            if T.live_threat:
                parts.append(LIVE_SCRIPT[L] if L in SCRIPT_LANGS else rng.choice(LIVE_EN if L == "en" else LIVE))
            return ", ".join(parts)
        if state == "threat_check":
            if L in SCRIPT_LANGS:
                return yes(L) if T.live_threat else no(L)
            return yes(L) if T.live_threat else (no(L) + (", call kat gaya" if L == "hi" else ", I cut the call"))
        if state == "amount":
            return say_amount(self.t.amount, L, rng)
        if state == "time":
            return say_minutes(self.t.minutes, L, rng)
        if state == "mode":
            if L in SCRIPT_LANGS:
                return MODE_S[L][self.t.mode]
            return {"UPI": "UPI", "Card": "card", "Net banking / IMPS / NEFT": "net banking"}[self.t.mode] \
                if L == "en" else T.mode_cue
        if state == "utr":
            return say_digits(self.t.utr, L, rng) if self.t.utr else dont_know(L)
        if state == "utr_confirm":
            heard = case.transactions[-1].utr
            if heard == self.t.utr:
                return yes(L)
            if rng.random() < 0.5:
                return no(L) + ", " + say_digits(self.t.utr, L, rng)
            return no(L)
        if state == "suspect":
            return say_suspect(T, rng)
        if state == "suspect_spell":
            from saathi.translit import spell_out
            name = T.suspect.split("@")[0]
            return spell_out(name, {"dev": "hi"}.get(L, L))
        if state == "suspect_confirm":
            s = case.suspect
            heard = s.upi or s.mobile or s.account
            if heard == T.suspect:
                return yes(L)
            if s.upi and (s.spell_check or s.spelled_by_caller):
                return no(L)      # the caller hears the letters and can tell they are wrong
            return no(L) + ", " + say_suspect(T, rng) if rng.random() < 0.5 else no(L)
        if state == "bank":
            return T.bank_cue
        if state == "more_txn":
            if self.txn_i + 1 < len(T.txns):
                self.txn_i += 1
                return yes(L)
            return no(L)
        if state == "summary":
            wrong = self._wrong_fields(dialog)
            if not wrong:
                return yes(L) if L in SCRIPT_LANGS else yes(L) + (", sab sahi hai" if L == "hi" else ", all correct")
            return no(L) + ", " + self._fix_phrase(wrong[0])
        if state == "fix_which":
            wrong = self._wrong_fields(dialog)
            return self._fix_phrase(wrong[0]) if wrong else yes(L)
        return yes(L)

    def _wrong_fields(self, dialog) -> List[str]:
        c = dialog.case
        wrong = []
        last = c.transactions[-1]
        truth = self.truth.txns[min(len(c.transactions), len(self.truth.txns)) - 1]
        if last.amount is not None and last.amount != truth.amount:
            wrong.append("amount")
        if last.utr is not None and truth.utr and last.utr != truth.utr:
            wrong.append("utr")
        heard = c.suspect.upi or c.suspect.mobile or c.suspect.account
        if heard and heard != self.truth.suspect:
            wrong.append("suspect")
        return wrong

    def _fix_phrase(self, field_name: str) -> str:
        L, rng = self.truth.lang, self.rng
        truth = self.truth.txns[-1]
        if L in SCRIPT_LANGS:
            word = {"amount": {"dev": "रकम", "pa": "ਰਕਮ", "ta": "தொகை"},
                    "utr": {"dev": "यूटीआर", "pa": "ਯੂਟੀਆਰ", "ta": "யுடிஆர்"},
                    "suspect": {"dev": "यूपीआई", "pa": "ਯੂਪੀਆਈ", "ta": "யுபிஐ"}}[field_name][L]
            return word + (" " + say_amount(truth.amount, L, rng) if field_name == "amount" else "")
        if field_name == "amount":
            return ("amount is " if L == "en" else "rakam ") + say_amount(truth.amount, L, rng) + ("" if L == "en" else " thi")
        if field_name == "utr":
            return "UTR " + ("is wrong" if L == "en" else "galat hai")
        return ("UPI ID is wrong" if L == "en" else "upi galat hai")
