"""Rule-based understanding of caller utterances (Hinglish, Hindi, English).

The rules are deliberately transparent: every decision can be explained to a
police officer or a judge, and the agent works even when no LLM is reachable.
Evon (Gnani's reasoning model) is layered on top for summaries and for fraud
narratives the rules cannot classify (see providers/llm.py).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from . import numbers as N
from . import translit as T
from . import validators as V

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _norm(text: str) -> str:
    return " " + " ".join(N.tokenize(text)) + " "


def _has_any(text_norm: str, phrases) -> List[str]:
    hits = []
    for p in phrases:
        p_norm = " " + " ".join(N.tokenize(p)) + " "
        if p_norm in text_norm:
            hits.append(p)
    return hits


PUNJABI_MARKERS = [" tuhada ", " tuhadi ", " mainu ", " sanu ", " hoya ", " ditte ", " kitte ", " ohne ",
                   " sade ", " pehlan ", " haanji ", " vich ", " nal ", " hun ", " kiven "]
TAMIL_MARKERS = [" enna ", " naan ", " ennoda ", " panam ", " poochu ", " pochu ", " aachu ", " illa ",
                 " aama ", " sollunga ", " vandhuchu ", " anuppunen ", " theriyala ", " munnadi ", " nimisham "]


def detect_language(text: str) -> str:
    if re.search(r"[\u0A00-\u0A7F]", text):
        return "pa"
    if re.search(r"[\u0B80-\u0BFF]", text):
        return "ta"
    if re.search(r"[\u0900-\u097F]", text):
        return "hi"
    t = _norm(text)
    if sum(1 for m in TAMIL_MARKERS if m in t) >= 2:
        return "ta"
    if sum(1 for m in PUNJABI_MARKERS if m in t) >= 2:
        return "pa"
    hindi_markers = [" hai ", " mera ", " mere ", " meri ", " se ", " ko ", " paise ", " gaye ",
                     " kat ", " nahi ", " haan ", " kya ", " tha ", " hua ", " kiya ",
                     " bola ", " wala ", " abhi ", " mujhe ", " maine ", " ke ", " ki ", " ka ", " pe ",
                     " aaya ", " bheja ", " bheje ", " karwaya ", " liye ", " naam ", " rahe ", " raha ",
                     " gaya ", " diya ", " diye ", " hain ", " mein ", " wale ", " bhi "]
    score = sum(1 for m in hindi_markers if m in t)
    return "hi" if score >= 1 else "en"


# ---------------------------------------------------------------------------
# fraud taxonomy (sub-category names modelled on the National Cybercrime
# Reporting Portal's "Online Financial Fraud" categories)
# ---------------------------------------------------------------------------

FRAUD_TYPES: Dict[str, dict] = {
    "digital_arrest": {
        "label": "Digital arrest / impersonation of police or agency",
        "ncrp": "Fraud Call/Vishing",
        "cues": ["digital arrest", "cbi", "ed officer", "enforcement directorate", "customs",
                 "police wale", "police officer", "video call pe police", "arrest warrant",
                 "parcel", "drugs", "money laundering", "narcotics", "trai", "mumbai police",
                 "aapke naam pe case", "डिजिटल अरेस्ट", "सीबीआई", "पार्सल", "पुलिस", "गिरफ्तार",
                 "ਡਿਜੀਟਲ ਅਰੈਸਟ", "ਸੀਬੀਆਈ", "ਪਾਰਸਲ", "ਪੁਲਿਸ", "டிஜிட்டல் அரெஸ்ட்", "சிபிஐ", "பார்சல்", "போலீஸ்"],
    },
    "bank_kyc_vishing": {
        "label": "Bank / KYC impersonation (vishing)",
        "ncrp": "Fraud Call/Vishing",
        "cues": ["kyc", "bank se call", "bank wala", "bank wale", "account band", "card block",
                 "pan update", "reward points", "credit card limit", "otp bataya", "otp diya",
                 "otp share", "otp de diya", "केवाईसी", "बैंक से", "ओटीपी", "ਕੇਵਾਈਸੀ", "ਓਟੀਪੀ",
                 "கேஒய்சி", "ஓடிபி", "otp sonnen", "otp koduthen"],
    },
    "upi_qr_collect": {
        "label": "UPI QR / collect-request fraud",
        "ncrp": "UPI Related Frauds",
        "cues": ["qr code", "qr scan", "scan kiya", "collect request", "request aayi", "pin dala",
                 "paise receive", "olx", "army officer", "refund ke liye pin", "क्यूआर", "पिन डाला"],
    },
    "investment_task": {
        "label": "Investment / task / trading scam",
        "ncrp": "UPI Related Frauds",
        "cues": ["investment", "trading", "stock tips", "telegram", "task", "like karne",
                 "youtube video like", "crypto", "double", "ipo", "high return", "profit",
                 "निवेश", "ट्रेडिंग", "टास्क"],
    },
    "job_fraud": {
        "label": "Fake job / registration fee",
        "ncrp": "UPI Related Frauds",
        "cues": ["job", "naukri", "registration fee", "work from home", "part time",
                 "offer letter", "नौकरी"],
    },
    "fake_customer_care": {
        "label": "Fake customer-care number",
        "ncrp": "Fraud Call/Vishing",
        "cues": ["customer care", "customer care number", "google pe number", "helpline number search",
                 "refund", "amazon", "flipkart", "swiggy", "zomato", "electricity bill", "bijli bill",
                 "कस्टमर केयर", "बिजली बिल"],
    },
    "card_sim_swap": {
        "label": "Card fraud / SIM swap",
        "ncrp": "Debit/Credit Card Fraud/Sim Swap Fraud",
        "cues": ["sim band", "sim swap", "network chala gaya", "card se paise", "debit card",
                 "credit card se", "card clone", "atm", "सिम बंद", "कार्ड"],
    },
    "remote_access": {
        "label": "Remote-access app takeover",
        "ncrp": "Internet Banking Related Fraud",
        "cues": ["anydesk", "any desk", "teamviewer", "team viewer", "quick support", "quicksupport",
                 "rustdesk", "airdroid", "screen share", "screen sharing", "app download karwaya",
                 "apk", "link pe click", "लिंक", "एनीडेस्क", "एनी डेस्क", "टीमव्यूअर", "टीम व्यूअर",
                 "क्विक सपोर्ट", "स्क्रीन शेयर", "रस्टडेस्क"],
    },
}

FRAUD_PRIORITY = ["digital_arrest", "remote_access", "upi_qr_collect", "investment_task",
                  "job_fraud", "fake_customer_care", "card_sim_swap", "bank_kyc_vishing"]


_LETTER_RUN = re.compile(r"(?:(?<=\s)|^)((?:[\u0900-\u097F]{1,2}\s+){1,}[\u0900-\u097F]{1,2})(?=\s|$|[,.।])")


def _join_spelled(t: str) -> str:
    """Prisma often spells acronyms as separate letters: "सी बी आई" -> "सीबीआई"."""
    return _LETTER_RUN.sub(lambda m: re.sub(r"\s+", "", m.group(1)), t)


def classify_fraud(text: str) -> Tuple[str, List[str]]:
    t = _norm(text)
    t = t + " " + _join_spelled(t)
    scored = []
    for key in FRAUD_PRIORITY:
        hits = _has_any(t, FRAUD_TYPES[key]["cues"])
        if hits:
            scored.append((len(hits), -FRAUD_PRIORITY.index(key), key, hits))
    if not scored:
        return "other", []
    scored.sort(reverse=True)
    _, _, key, hits = scored[0]
    return key, hits


# ---------------------------------------------------------------------------
# live threat: the scam is still happening *during* the 1930 call
# ---------------------------------------------------------------------------

LIVE_THREAT_CUES = [
    "abhi bhi call pe", "abhi bhi call par", "abhi bhi video call", "abhi bhi line pe",
    "abhi bhi baat", "still on call", "still on the call", "still on video call",
    "video call chal raha", "video call chal rahi", "video call on hai", "call chal raha",
    "camera on rakho", "camera on rakhne", "kisi ko mat batao", "kisi ko mat bataana",
    "ghar se bahar mat", "room mein band", "aur paise maang raha", "aur paise maang rahe",
    "aur paise bhejne", "otp maang raha", "otp maang rahe", "abhi bhi otp",
    "anydesk", "any desk", "teamviewer", "team viewer", "quick support", "screen share",
    "screen sharing", "rustdesk", "airdroid",
    "अभी भी कॉल", "वीडियो कॉल चल", "किसी को मत बताओ", "और पैसे मांग",
    "hale vi call", "hale vi video call", "ਹਾਲੇ ਵੀ ਕਾਲ", "ਹਾਲੇ ਵੀ ਵੀਡੀਓ ਕਾਲ", "ਹੋਰ ਪੈਸੇ ਮੰਗ",
    "innum call la", "innum video call", "இன்னும் கால்", "இன்னும் வீடியோ கால்", "இன்னும் பணம் கேக்க",
]

REMOTE_APPS = ["anydesk", "any desk", "teamviewer", "team viewer", "quick support", "rustdesk", "airdroid",
               "screen share", "screen sharing"]


@dataclass
class ThreatResult:
    live: bool
    remote_app: bool
    cues: List[str] = field(default_factory=list)


def detect_live_threat(text: str) -> ThreatResult:
    t = _norm(text)
    t = t + " " + _join_spelled(t)
    cues = _has_any(t, LIVE_THREAT_CUES)
    remote = bool(_has_any(t, REMOTE_APPS))
    return ThreatResult(live=bool(cues), remote_app=remote, cues=cues)


# ---------------------------------------------------------------------------
# yes / no / don't know / repeat / correction
# ---------------------------------------------------------------------------

YES = ["haan", "han", "ha", "haanji", "haan ji", "ji haan", "yes", "yeah", "yup", "sahi hai",
       "sahi", "correct", "right", "theek hai", "thik hai", "bilkul", "ok", "okay", "हाँ", "हां",
       "जी हाँ", "सही है", "सही", "ठीक है", "ਹਾਂ", "ਹਾਂਜੀ", "ਹਾਂ ਜੀ", "ਸਹੀ ਹੈ", "ਠੀਕ ਹੈ", "sahi aa", "theek aa",
       "aama", "aamaa", "aam", "sari", "ஆமா", "ஆம்", "ஆமாம்", "சரி", "சரிதான்"]
NO = ["nahi", "nahin", "nai", "na", "no", "galat", "wrong", "not correct", "नहीं", "गलत", "ना",
      "ਨਹੀਂ", "ਨਹੀ", "ਗਲਤ", "illa", "illai", "thappu", "இல்லை", "இல்ல", "தப்பு"]
DONT_KNOW = ["pata nahi", "pata nahin", "nahi pata", "nahin pata", "yaad nahi", "yaad nahin",
             "don't know", "dont know", "not sure", "maloom nahi", "nahi maloom", "पता नहीं",
             "याद नहीं", "मालूम नहीं", "skip", "ਪਤਾ ਨਹੀਂ", "ਯਾਦ ਨਹੀਂ", "theriyala", "theriyadhu",
             "தெரியல", "தெரியாது", "ஞாபகம் இல்ல"]
REPEAT = ["dobara", "phir se", "fir se", "repeat", "again", "samjha nahi", "samajh nahi",
          "kya bola", "kya kaha", "दोबारा", "फिर से", "समझ नहीं", "ਦੁਬਾਰਾ", "ਸਮਝ ਨਹੀਂ",
          "thirumba", "marubadiyum", "திரும்ப", "மறுபடியும்", "புரியல"]
CORRECTION = ["nahi nahi", "galat", "sorry", "matlab", "i mean", "actually", "asal mein",
              "nahi woh", "गलत", "नहीं नहीं"]


def is_dont_know(text: str) -> bool:
    return bool(_has_any(_norm(text), DONT_KNOW))


def is_repeat(text: str) -> bool:
    return bool(_has_any(_norm(text), REPEAT))


def yes_no(text: str) -> Optional[bool]:
    t = _norm(text)
    if is_dont_know(text):
        return None
    no_hits = _has_any(t, NO)
    yes_hits = _has_any(t, YES)
    if no_hits and not yes_hits:
        return False
    if yes_hits and not no_hits:
        return True
    if no_hits and yes_hits:
        # "nahi, sahi hai" is rare; "haan nahi" ambiguous -> treat first occurrence
        # both present: the LAST one wins ("haan to... nahi", "umm haan, nahi nahi") because
        # fillers come first and people correct themselves
        last_no = max(t.rfind(" " + " ".join(N.tokenize(p)) + " ") for p in no_hits)
        last_yes = max(t.rfind(" " + " ".join(N.tokenize(p)) + " ") for p in yes_hits)
        return last_yes > last_no
    return None


SLOT_MENTIONS = {
    "amount": ["amount", "rakam", "paise", "rupaye", "kitne", "रकम", "पैसे", "राशि", "ਰਕਮ", "ਪੈਸੇ", "தொகை", "பணம்"],
    "time": ["time", "samay", "waqt", "kab", "baje", "ghante", "minute", "समय", "बजे", "ਸਮਾਂ", "ਵਜੇ", "நேரம்"],
    "utr": ["utr", "reference", "ref", "transaction id", "txn", "यूटीआर", "रेफरेंस", "ਯੂਟੀਆਰ", "யுடிஆர்"],
    "suspect": ["upi id", "upi", "uska number", "fraud ka number", "account", "jisko", "यूपीआई", "अकाउंट",
                "ਯੂਪੀਆਈ", "ਅਕਾਊਂਟ", "யுபிஐ", "அக்கவுண்ட்"],
    "bank": ["bank", "बैंक", "ਬੈਂਕ", "பேங்க்", "வங்கி"],
    "mode": ["mode", "kaise bheje", "phonepe", "gpay", "card", "netbanking"],
}


def mentioned_slots(text: str) -> List[str]:
    t = _norm(text)
    return [slot for slot, cues in SLOT_MENTIONS.items() if _has_any(t, cues)]


# ---------------------------------------------------------------------------
# payment mode and bank
# ---------------------------------------------------------------------------

PAYMENT_MODES = {
    "UPI": ["upi", "phonepe", "phone pe", "gpay", "google pay", "paytm", "bhim", "amazon pay",
            "qr", "यूपीआई", "फोनपे", "गूगल पे", "पेटीएम", "ਯੂਪੀਆਈ", "ਫੋਨਪੇ", "ਗੂਗਲ ਪੇ", "ਪੇਟੀਐਮ",
            "யுபிஐ", "போன்பே", "ஜிபே", "கூகுள் பே", "பேடிஎம்"],
    "Card": ["debit card", "credit card", "card", "atm", "कार्ड", "ਕਾਰਡ", "கார்டு"],
    "Net banking / IMPS / NEFT": ["net banking", "netbanking", "imps", "neft", "rtgs",
                                  "internet banking", "नेट बैंकिंग", "ਨੈੱਟ ਬੈਂਕਿੰਗ", "நெட் பேங்கிங்"],
    "Wallet": ["wallet", "mobikwik", "वॉलेट"],
    "AePS (Aadhaar / fingerprint)": ["aeps", "aadhaar se", "angootha", "fingerprint", "अंगूठा"],
}


def detect_payment_mode(text: str) -> Optional[str]:
    t = _norm(text)
    for mode, cues in PAYMENT_MODES.items():
        if _has_any(t, cues):
            return mode
    return None


BANKS = {
    "State Bank of India": ["sbi", "state bank", "एसबीआई", "स्टेट बैंक", "ਐਸਬੀਆਈ", "ਸਟੇਟ ਬੈਂਕ", "எஸ்பிஐ", "ஸ்டேட் பேங்க்"],
    "HDFC Bank": ["hdfc", "एचडीएफसी", "ਐਚਡੀਐਫਸੀ", "எச்டிஎஃப்சி"],
    "ICICI Bank": ["icici", "आईसीआईसीआई", "ਆਈਸੀਆਈਸੀਆਈ", "ஐசிஐசிஐ"],
    "Axis Bank": ["axis", "एक्सिस"],
    "Punjab National Bank": ["pnb", "punjab national", "पंजाब नेशनल", "ਪੰਜਾਬ ਨੈਸ਼ਨਲ", "ਪੀਐਨਬੀ"],
    "Bank of Baroda": ["bank of baroda", "bob", "baroda", "बड़ौदा", "बड़ोदा"],
    "Canara Bank": ["canara", "केनरा", "கனரா"],
    "Union Bank of India": ["union bank", "यूनियन बैंक"],
    "Kotak Mahindra Bank": ["kotak", "कोटक"],
    "Yes Bank": ["yes bank", "यस बैंक"],
    "IndusInd Bank": ["indusind", "इंडसइंड"],
    "IDFC First Bank": ["idfc"],
    "Bank of India": ["bank of india", "boi", "बैंक ऑफ इंडिया"],
    "Indian Bank": ["indian bank", "इंडियन बैंक", "இந்தியன் பேங்க்"],
    "Indian Overseas Bank": ["indian overseas", "iob", "இந்தியன் ஓவர்சீஸ்", "ஐஓபி"],
    "Tamilnad Mercantile Bank": ["tamilnad mercantile", "tmb"],
    "City Union Bank": ["city union", "cub bank"],
    "Central Bank of India": ["central bank"],
    "UCO Bank": ["uco"],
    "IDBI Bank": ["idbi"],
    "Punjab & Sind Bank": ["punjab and sind", "punjab sind", "पंजाब एंड सिंध", "ਪੰਜਾਬ ਐਂਡ ਸਿੰਧ"],
    "Federal Bank": ["federal bank"],
    "AU Small Finance Bank": ["au bank", "au small finance"],
    "RBL Bank": ["rbl"],
    "India Post Payments Bank": ["india post", "ippb", "post office", "डाकघर"],
    "Paytm Payments Bank": ["paytm payments bank", "paytm bank"],
    "Airtel Payments Bank": ["airtel payments bank", "airtel bank"],
}


def detect_bank(text: str) -> Optional[str]:
    t = _norm(text)
    # longest cue first so "bank of india" beats "indian bank"/"india post"
    best = None
    best_len = 0
    for bank, cues in BANKS.items():
        for c in _has_any(t, cues):
            if len(c) > best_len:
                best, best_len = bank, len(c)
    return best


# ---------------------------------------------------------------------------
# time of the transaction
# ---------------------------------------------------------------------------

_UNIT_MIN = {"minute": 1, "minutes": 1, "min": 1, "mins": 1, "minat": 1, "mint": 1, "मिनट": 1,
             "ghanta": 60, "ghante": 60, "ghanto": 60, "hour": 60, "hours": 60, "hr": 60, "hrs": 60,
             "घंटा": 60, "घंटे": 60, "din": 1440, "day": 1440, "days": 1440, "दिन": 1440,
             "ਮਿੰਟ": 1, "ਘੰਟਾ": 60, "ਘੰਟੇ": 60, "ਦਿਨ": 1440, "nimisham": 1, "nimishathukku": 1, "நிமிஷம்": 1,
             "நிமிடம்": 1, "நிமிஷத்துக்கு": 1, "naal": 1440, "நாள்": 1440}
_AGO = {"pehle", "pahle", "phele", "ago", "back", "hue", "hua", "hogaye", "पहले", "हुए", "हुआ"}


def parse_minutes_ago(text: str, now: Optional[datetime] = None) -> Optional[int]:
    """Minutes between the transaction and now, from relative or clock expressions."""
    now = now or datetime.now()
    text = re.sub(r"(mani|மணி)\s+(neram|நேரம்)", "ghante", text)   # Tamil "rendu mani neram" = 2 hours
    toks = N.tokenize(text)
    t = _norm(text)
    if _has_any(t, ["abhi abhi", "just now", "abhi turant", "abhi hi", "अभी अभी", "थोड़ी देर पहले",
                    "thodi der pehle", "few minutes ago", "hune hune", "ਹੁਣੇ ਹੁਣੇ", "ippo thaan", "இப்போ தான்"]):
        return 5
    # "<number> <unit> pehle" (number may be words or fractions: "aadha ghanta", "dedh ghanta")
    for i, tok in enumerate(toks):
        if tok in _UNIT_MIN:
            unit = _UNIT_MIN[tok]
            val = None
            j = i - 1
            if j >= 0:
                prev = toks[j]
                if N._is_numeric(prev):
                    val = float(prev)
                elif prev in N.FRACTION_WORDS:
                    val = N.FRACTION_WORDS[prev]
                elif prev in N.FRACTION_PREFIX:        # "paune ghante" = 45 min, "sava ghanta" = 75 min
                    val = 1 + N.FRACTION_PREFIX[prev]
                elif prev in N.WORD_TO_NUM:
                    val = float(N.WORD_TO_NUM[prev])
                    if j - 1 >= 0 and toks[j - 1] in N.FRACTION_PREFIX:
                        val += N.FRACTION_PREFIX[toks[j - 1]]
            if val is None and j - 1 >= 0 and toks[j - 1] in N.FRACTION_WORDS and toks[j] in ("an", "a", "ek"):
                val = N.FRACTION_WORDS[toks[j - 1]]          # "half an hour"
            if val is None and tok in ("ghanta", "hour", "घंटा", "ghante"):
                val = 1.0  # "ek ghanta" often said as "ghanta bhar pehle"
            if val is not None:
                return int(round(val * unit))
    clock_words = ("baje", "बजे", "vaje", "ਵਜੇ", "manikku", "மணிக்கு")
    for i, tok in enumerate(toks[1:], 1):
        if tok in clock_words and toks[i - 1] in N.WORD_TO_NUM and N.WORD_TO_NUM[toks[i - 1]] <= 12:
            text = f"{N.WORD_TO_NUM[toks[i - 1]]} {tok} " + text   # "दस बजे" -> "10 बजे"
            break
    if _has_any(t, ["kal raat", "last night", "कल रात", "ਕੱਲ੍ਹ ਰਾਤ", "nethu raathiri", "நேத்து ராத்திரி"]):
        return 18 * 60
    if _has_any(t, ["kal", "yesterday", "कल", "ਕੱਲ੍ਹ", "nethu", "நேத்து", "நேற்று"]):
        return 24 * 60
    # clock time: "11 baje", "subah 11:30", "shaam 4 baje", "3 pm"
    m = re.search(r"(\d{1,2})(?:[:.](\d{2}))?\s*(?:baje|बजे|vaje|ਵਜੇ|manikku|மணிக்கு|o'?clock|am|pm|a m|p m)", N.normalize(text))
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2) or 0)
        norm = N.normalize(text)
        if any(w in norm for w in ("shaam", "sham", "raat", "dopahar", "dopehar", "pm", "p m",
                                   "शाम", "रात", "दोपहर", "ਸ਼ਾਮ", "ਰਾਤ", "ਦੁਪਹਿਰ", "raathiri",
                                   "மாலை", "ராத்திரி", "மதியம்")) and hour < 12:
            hour += 12
        if hour > 23 or minute > 59:
            return None
        then = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if then > now:
            then -= timedelta(days=1)
        return int((now - then).total_seconds() // 60)
    return None


def describe_minutes(minutes: int, lang: str = "hi") -> str:
    from .prompts import p
    if minutes < 60:
        return p(lang, "minutes_ago", m=minutes)
    h, m = divmod(minutes, 60)
    if h >= 24:
        return p(lang, "days_ago", d=h // 24)
    return p(lang, "hours_min_ago", h=h, m=m) if m else p(lang, "hours_ago", h=h)


# ---------------------------------------------------------------------------
# suspect identifiers: UPI ID, phone, account number
# ---------------------------------------------------------------------------

_AT_WORDS = ["at the rate of", "at the rate", "at rate", "attherate", "at d rate", "at da rate",
             "एट द रेट", "एट दी रेट", "ऐट द रेट", "ਐਟ ਦ ਰੇਟ", "ਐਟ ਦੀ ਰੇਟ", "அட் த ரேட்", "அட் தி ரேட்",
             "ஆட் த ரேட்"]
_DOT_WORDS = ["dot", "डॉट", "point", "ਡਾਟ", "ਡੌਟ", "டாட்"]
_HANDLE_STOP = {"mera", "meri", "upi", "id", "hai", "tha", "ka", "ki", "ke", "uska", "uski",
                "account", "number", "the", "is", "on", "pe", "par", "me", "mein", "to", "ko",
                "jisko", "jiske", "paise", "gaye", "bheje", "bhej", "diye", "unka", "unki", "wo",
                "woh", "vo", "ye", "yeh", "ne", "se", "aur", "and", "naam", "name", "hain"}


_HANDLE_STOP_DEV = {"है", "था", "थी", "का", "की", "के", "मेरा", "मेरी", "उसका", "उसकी", "आईडी", "यूपीआई",
                    "पर", "पे", "में", "को", "ने", "से", "और", "नंबर", "अकाउंट", "जिसको", "पैसे", "गए", "भेजे", "वो",
                    "ਹੈ", "ਸੀ", "ਦਾ", "ਦੀ", "ਮੇਰਾ", "ਉਸਦਾ", "ਉਸਦੀ", "ਆਈਡੀ", "ਯੂਪੀਆਈ", "ਨੰਬਰ",
                    "அவங்க", "அவரோட", "ஐடி", "யுபிஐ", "நம்பர்", "தான்", "என்",
                    # fillers (जी/ਜੀ are also the letter G: the letter-run check keeps them when spelled)
                    "जी", "मतलब", "ਜੀ", "ਮਤਲਬ", "அது", "வந்து", "ம்ம்", "umm", "uh", "matlab", "ji"}
_UNDERSCORE_WORDS = ["underscore", "अंडरस्कोर", "अंडर स्कोर"]


def _is_stop(tok: str) -> bool:
    return tok in _HANDLE_STOP or tok in _HANDLE_STOP_DEV


def _latinize_left(tokens: List[str]) -> str:
    """Name part of a UPI ID: Latin kept, digit words -> digits, spelled letters -> letters, Devanagari transliterated."""
    out: List[str] = []
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t in (".", "_", "-"):
            out.append(t)
            i += 1
            continue
        # run of spelled letter names: "आर के" -> "rk"
        j = i
        while j < len(tokens) and T.is_letter_name(tokens[j]) and tokens[j] not in N.WORD_TO_NUM:
            j += 1
        if j - i >= 2 or (j - i == 1 and len(tokens) == 1):
            out.append(T.letters_from_names(tokens[i:j]))
            i = j
            continue
        val = N.WORD_TO_NUM.get(t)
        if val is not None and val < 10 and t != "do":
            out.append(str(val))
        elif T.is_devanagari(t):
            out.append(T.transliterate(t))
        else:
            out.append(t)
        i += 1
    return "".join(out).strip("._-")


def extract_upi(text: str) -> Optional[str]:
    s = " " + N.normalize(text) + " "
    # Prisma may write "@" glued to Devanagari ("रमेश@ybl") or spell it out
    s = s.replace("@", " @ ")
    for w in sorted(_AT_WORDS, key=len, reverse=True):
        s = s.replace(" " + w + " ", " @ ")
    # bare "at" only when followed by a known UPI handle: "amit123 at ybl"
    s = re.sub(r" at (?=(" + "|".join(sorted(V.KNOWN_UPI_HANDLES, key=len, reverse=True)) + r") )", " @ ", s)
    for w in _DOT_WORDS:
        s = s.replace(" " + w + " ", " . ")
    for w in _UNDERSCORE_WORDS:
        s = s.replace(w, " _ ")
    s = re.sub(r"(?<=[a-z0-9])\.(?=[a-z0-9])", " . ", s)
    s = re.sub(r"(?<=[a-z0-9])_(?=[a-z0-9])", " _ ", s)
    if "@" not in s:
        return None
    toks = [t for t in re.split(r"\s+", s) if t]
    at = toks.index("@")
    # right side: up to 4 tokens until a stop word -> best known handle
    right: List[str] = []
    for t in toks[at + 1: at + 5]:
        if _is_stop(t) or t in (".", "@"):
            break
        right.append(t)
    handle = T.resolve_handle(right, V.KNOWN_UPI_HANDLES)
    # left side: walk back until a stop word
    left: List[str] = []
    k = at - 1
    # spelled letters right before '@' ("आर के एट द रेट ...") may include words that are
    # also Hindi stop words (के = "of"), so take a run of >= 2 letter names first
    run = 0
    while k - run >= 0 and T.is_letter_name(toks[k - run]):
        run += 1
    if run >= 2:
        left = toks[k - run + 1: k + 1]
        k -= run
    while k >= 0:
        tok = toks[k]
        if _is_stop(tok):
            letter_run = T.is_letter_name(tok) and (
                (k - 1 >= 0 and T.is_letter_name(toks[k - 1])) or (left and T.is_letter_name(left[0])))
            if not letter_run:
                break
        if tok in (".", "_", "-") or re.fullmatch(r"[a-z0-9]+", tok) or T.is_devanagari(tok):
            left.insert(0, tok)
        else:
            break
        k -= 1
    name = _latinize_left(left)
    if len(name) < 2 or not handle:
        return None
    global _LAST_UPI_PHONETIC
    _LAST_UPI_PHONETIC = any(T.is_devanagari(t) and not T.is_letter_name(t) for t in left)
    return f"{name}@{handle}"


_LAST_UPI_PHONETIC = False


def upi_needs_spelling(text: str) -> bool:
    """True when the name part of the UPI ID was guessed from Indic-script sounds
    (रिफंड -> 'rifand'), so the exact Latin spelling must be confirmed letter by letter."""
    global _LAST_UPI_PHONETIC
    _LAST_UPI_PHONETIC = False
    extract_upi(text)
    return _LAST_UPI_PHONETIC


@dataclass
class Suspect:
    upi: Optional[str] = None
    mobile: Optional[str] = None
    account: Optional[str] = None

    def any(self) -> bool:
        return bool(self.upi or self.mobile or self.account)

    def identifiers(self) -> List[Tuple[str, str]]:
        out = []
        if self.upi:
            out.append(("upi", self.upi))
        if self.mobile:
            out.append(("mobile", self.mobile))
        if self.account:
            out.append(("account", self.account))
        return out


def extract_suspect(text: str, allow_12_digit_account: bool = False) -> Suspect:
    """UPI ID, mobile or account number. A bare 12-digit run is usually a UTR, so it only
    counts as an account number when we explicitly asked where the money went."""
    s = Suspect()
    upi = extract_upi(text)
    if upi and V.check_upi(upi).ok:
        s.upi = upi
    rest = text
    for run in N.spoken_digit_runs(rest):
        if s.upi and run in s.upi:
            continue
        mob = V.check_mobile(run)
        if mob.ok and not s.mobile:
            s.mobile = mob.value
            continue
        acc = V.check_account(run)
        if acc.ok and not s.account and (len(run) != 12 or allow_12_digit_account):
            s.account = acc.value
    return s


# ---------------------------------------------------------------------------
# one-shot extraction of everything present in an utterance
# ---------------------------------------------------------------------------


def _utr_from(text: str):
    """Pick the UTR out of an utterance that may also contain the amount.

    Prisma writes numbers as digits, so "₹45,000 कट गए, UTR 412356789012" arrives as
    two digit runs. Joining every run would give a 17-digit "UTR". Instead:
    1. a run that is already a valid UTR wins;
    2. runs that are the money amount (₹ / rupaye / hazaar next to them) are dropped;
    3. what is left is joined, which keeps "4123 5678 9012" said in groups working.
    """
    runs = N.spoken_digit_runs(text)
    if not runs:
        return None, None
    for r in runs:
        chk = V.check_utr(r)
        if chk.ok:
            return chk.value, None
    money = {str(a.value) for a in N.find_amounts(text) if a.has_currency or a.has_scale}
    kept = [r for r in runs if r not in money] if len(runs) > 1 else runs
    digits = "".join(kept)
    chk = V.check_utr(digits)
    if chk.ok:
        return chk.value, None
    return None, (digits or None)


@dataclass
class Extraction:
    amount: Optional[int] = None
    minutes_ago: Optional[int] = None
    utr: Optional[str] = None
    utr_partial: Optional[str] = None
    mode: Optional[str] = None
    bank: Optional[str] = None
    suspect: Suspect = field(default_factory=Suspect)
    fraud_type: str = "other"
    fraud_cues: List[str] = field(default_factory=list)
    threat: ThreatResult = field(default_factory=lambda: ThreatResult(False, False))


def extract_all(text: str, expecting: Optional[str] = None, now: Optional[datetime] = None) -> Extraction:
    ex = Extraction()
    ex.amount = N.parse_amount(text, expecting_amount=(expecting == "amount"))
    ex.minutes_ago = parse_minutes_ago(text, now)
    ex.mode = detect_payment_mode(text)
    ex.bank = detect_bank(text)
    ex.fraud_type, ex.fraud_cues = classify_fraud(text)
    ex.threat = detect_live_threat(text)

    # UTR: when we are asking for it, take all digits; otherwise only an exact 12-digit run
    if expecting == "utr":
        ex.utr, ex.utr_partial = _utr_from(text)
    else:
        for run in N.spoken_digit_runs(text):
            if len(run) == 12:
                ex.utr = run
                break

    if expecting == "suspect" or "@" in text or _has_any(_norm(text), _AT_WORDS):
        ex.suspect = extract_suspect(text, allow_12_digit_account=(expecting == "suspect"))
    else:
        # outside the suspect question, only accept an explicit UPI id
        upi = extract_upi(text)
        if upi and V.check_upi(upi).ok:
            ex.suspect.upi = upi

    # an amount must not be the time ("20 minute") or part of the UTR
    if ex.amount is not None and ex.minutes_ago is not None and expecting != "amount":
        if re.search(rf"\b{ex.amount}\s*(minute|min|ghant|hour|baje)", N.normalize(text)):
            ex.amount = None
    return ex
