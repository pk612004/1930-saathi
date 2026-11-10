"""The 1930 Saathi conversation engine.

A slot-filling dialog built for panicked callers:

* golden-hour essentials first (amount, time, UTR, where the money went)
* opportunistic filling: anything said early is captured, never asked twice
* validator-aware re-prompts ("I heard 11 digits, a UTR has 12")
* immediate read-back of the two error-prone identifiers (UTR, fraudster ID)
* a final summary read-back with targeted correction ("UTR galat hai")
* a live-threat interrupt when the scam is still in progress
* never traps the caller: after two failed tries a field is marked unknown
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import re
from typing import Dict, List, Optional

from . import extract as X
from . import numbers as N
from . import validators as V
from .models import Case, Transaction, Turn
from .prompts import PROMPTS, p

MAX_RETRIES = 2
MAX_TXNS = 5


@dataclass
class Reply:
    text: str
    state: str
    done: bool = False
    events: List[Dict] = field(default_factory=list)


def speak_upi(vpa: str, lang: str) -> str:
    at_w, dot_w = p(lang, "at_word"), p(lang, "dot_word")
    out = []
    for ch in vpa:
        if ch == "@":
            out.append(f" {at_w} ")
        elif ch == ".":
            out.append(f" {dot_w} ")
        elif ch.isdigit():
            out.append(" " + N.speak_digits(ch, lang) + " ")
        else:
            out.append(ch)
    return " ".join("".join(out).split())


def speak_identifier(kind: str, value: str, lang: str, spell: bool = False) -> str:
    if kind == "upi" and spell:
        from .translit import spell_out
        name, handle = value.split("@", 1)
        return f"{spell_out(name, lang)}, {p(lang, 'at_word')} {handle}"
    if kind == "upi":
        return speak_upi(value, lang)
    return N.speak_digits(value, lang, group=5 if kind == "mobile" else 4)


def speak_case_id(case_id: str, lang: str) -> str:
    tail = case_id.split("-")[-1]
    spoken = []
    for ch in tail:
        spoken.append(N.speak_digits(ch, lang) if ch.isdigit() else ch)
    return " ".join(spoken)


class Dialog:
    def __init__(self, case: Optional[Case] = None, now_fn=datetime.now, lang: Optional[str] = None, llm=None):
        self.case = case or Case(call_started_at=now_fn().isoformat(timespec="seconds"))
        self.now_fn = now_fn
        self.state = "open"
        self.retries: Dict[str, int] = {}
        self.fixing: Optional[str] = None   # slot being corrected from the summary
        self.lang_locked = lang is not None
        if lang:
            self.case.lang = lang
        self.last_prompt = p(self.case.lang, "open")
        self.turns = 0
        self.llm = llm

    # ------------------------------------------------------- LLM fallback
    def _llm_value(self, slot: str, u: str, events: List[Dict]):
        """Rules found nothing: ask Evon, but accept only what the validators accept."""
        if self.llm is None or not u or X.is_dont_know(u):
            return None
        data = self.llm.extract_slot(slot, u, self.lang)
        if not data:
            return None
        if slot == "suspect":
            s = X.Suspect()
            if data.get("upi") and V.check_upi(str(data["upi"])).ok:
                s.upi = str(data["upi"]).lower()
            if data.get("mobile") and V.check_mobile(str(data["mobile"])).ok:
                s.mobile = V.check_mobile(str(data["mobile"])).value
            if data.get("account") and V.check_account(str(data["account"])).ok:
                s.account = V.check_account(str(data["account"])).value
            val = s if s.any() else None
        else:
            raw = data.get("value")
            val = None
            if raw is not None:
                if slot == "amount":
                    try:
                        v = int(float(raw))
                        val = v if V.check_amount(v).ok else None
                    except (TypeError, ValueError):
                        val = None
                elif slot == "time":
                    try:
                        v = int(float(raw))
                        val = v if 0 <= v <= 7 * 24 * 60 else None
                    except (TypeError, ValueError):
                        val = None
                elif slot == "utr":
                    chk = V.check_utr(str(raw))
                    # the digits must actually appear in what Prisma heard (no invented numbers)
                    val = chk.value if chk.ok and chk.value in N.all_digits(u) + re.sub(r"\D", "", u) else None
                elif slot == "bank":
                    val = X.detect_bank(str(raw)) or (str(raw) if str(raw) in X.BANKS else None)
                elif slot == "mode":
                    val = str(raw) if str(raw) in X.PAYMENT_MODES else X.detect_payment_mode(str(raw))
        if val is not None:
            self.case.field_sources[slot] = "llm"
            events.append({"type": "llm_fallback", "field": slot})
        return val

    # ------------------------------------------------------------------ utils
    @property
    def lang(self) -> str:
        return self.case.lang

    @property
    def txn(self) -> Transaction:
        return self.case.transactions[-1]

    def _now(self) -> datetime:
        return self.now_fn()

    def _log(self, role: str, text: str, **meta):
        self.case.transcript.append(Turn(role, text, self._now().isoformat(timespec="seconds"), meta))

    def greeting(self) -> Reply:
        text = p(self.lang, "open")
        self.last_prompt = text
        self._log("agent", text, state=self.state)
        return Reply(text, self.state)

    def _bump(self, key: str) -> int:
        self.retries[key] = self.retries.get(key, 0) + 1
        return self.retries[key]

    # --------------------------------------------------------- slot setters
    def _set_amount(self, amount: int):
        self.txn.amount = amount
        self.txn.amount_status = "captured"

    def _set_time(self, minutes: int):
        self.txn.minutes_ago = minutes
        self.txn.time_status = "captured"
        self.txn.txn_time = (self._now() - timedelta(minutes=minutes)).isoformat(timespec="seconds")

    def _set_mode(self, mode: str):
        self.txn.mode = mode
        self.txn.mode_status = "captured"

    def _set_bank(self, bank: str):
        self.case.victim_bank = bank
        self.case.bank_status = "captured"

    def _set_fraud(self, ftype: str, cues: List[str]):
        if ftype == "other":
            return
        info = X.FRAUD_TYPES[ftype]
        self.case.fraud_type = ftype
        self.case.fraud_label = info["label"]
        self.case.ncrp_subcategory = info["ncrp"]
        self.case.fraud_cues = sorted(set(self.case.fraud_cues) | set(cues))

    # ------------------------------------------------------ opportunistic fill
    def _absorb(self, ex: X.Extraction, expecting: Optional[str]) -> List[str]:
        """Fill any empty slot from what the caller volunteered. Returns filled slot names."""
        filled = []
        t = self.txn
        if self.case.fraud_type == "other" and ex.fraud_type != "other":
            self._set_fraud(ex.fraud_type, ex.fraud_cues)
        if ex.amount is not None and t.amount_status == "missing" and expecting not in ("utr", "suspect"):
            if V.check_amount(ex.amount).ok:
                self._set_amount(ex.amount)
                filled.append("amount")
        if ex.minutes_ago is not None and t.time_status == "missing":
            self._set_time(ex.minutes_ago)
            filled.append("time")
        if ex.mode and t.mode_status == "missing":
            self._set_mode(ex.mode)
            filled.append("mode")
        if ex.bank and self.case.bank_status == "missing" and expecting != "suspect":
            self._set_bank(ex.bank)
            filled.append("bank")
        if ex.utr and t.utr_status == "missing" and expecting != "utr":
            t.utr = ex.utr
            t.utr_first_heard = t.utr_first_heard or ex.utr
            t.utr_status = "pending_confirm"
            filled.append("utr")
        if ex.suspect.upi and self.case.suspect.status == "missing" and expecting != "suspect":
            self.case.suspect.spell_check = X.upi_needs_spelling(self._last_utterance)
            self.case.suspect.upi = ex.suspect.upi
            self.case.suspect.first_heard = self.case.suspect.first_heard or ex.suspect.upi
            self.case.suspect.status = "pending_confirm"
            filled.append("suspect")
        return filled

    def _infer_mode(self):
        t = self.txn
        if t.mode_status != "missing":
            return
        if self.case.suspect.upi or (t.utr and len(t.utr) == 12 and self.case.fraud_type in
                                     ("upi_qr_collect", "investment_task", "job_fraud")):
            self._set_mode("UPI")

    # ------------------------------------------------------------ threat
    def _threat_message(self) -> str:
        if self.case.remote_app:
            return p(self.lang, "threat_remote")
        if self.case.fraud_type == "digital_arrest":
            return p(self.lang, "threat_digital_arrest")
        return p(self.lang, "threat_generic")

    # -------------------------------------------------------- next question
    def _next_state(self) -> str:
        t = self.txn
        c = self.case
        if (not c.threat_checked and not c.live_threat and
                c.fraud_type in ("digital_arrest", "remote_access", "bank_kyc_vishing")):
            return "threat_check"
        if t.amount_status == "missing":
            return "amount"
        if t.time_status == "missing":
            return "time"
        if t.utr_status == "pending_confirm":
            return "utr_confirm"
        if c.suspect.status == "pending_confirm":
            return "suspect_confirm"
        self._infer_mode()
        if t.mode_status == "missing":
            return "mode"
        if t.utr_status == "missing":
            return "utr"
        if c.suspect.status == "missing":
            return "suspect"
        if c.bank_status == "missing":
            return "bank"
        if getattr(self, "_more_asked", 0) < len(c.transactions):
            return "more_txn"
        return "summary"

    def _prompt_for(self, state: str) -> str:
        t = self.txn
        if state == "amount":
            return p(self.lang, "amount_next" if len(self.case.transactions) > 1 else "amount")
        if state == "utr_confirm":
            return p(self.lang, "utr_confirm", digits=N.speak_digits(t.utr, self.lang))
        if state == "suspect_confirm":
            kind, value = self.case.suspect.primary()
            spell = kind == "upi" and (self.case.suspect.spell_check or self.case.suspect.spelled_by_caller)
            label = PROMPTS.get(self.lang, PROMPTS["hi"])["kinds"][kind]
            if spell:
                label = f"{label} ({p(self.lang, 'spelled')})"
            return p(self.lang, "suspect_confirm", kind=label, value=speak_identifier(kind, value, self.lang, spell))
        if state == "summary":
            return p(self.lang, "summary", summary=self.summary_sentence(spoken=True))
        if state == "suspect_spell":
            return p(self.lang, "spell_upi")
        return p(self.lang, state)

    def summary_sentence(self, spoken: bool = False) -> str:
        c = self.case
        L = self.lang
        unk = PROMPTS.get(L, PROMPTS["hi"])["unknown"]
        parts = []
        for i, t in enumerate(c.transactions, 1):
            amt = (N.speak_amount(t.amount, L) if spoken else f"₹{N.format_inr(t.amount)}") if t.amount else unk
            when = X.describe_minutes(t.minutes_ago, L) if t.minutes_ago is not None else unk
            utr = (N.speak_digits(t.utr, L) if spoken else t.utr) if t.utr else unk
            prefix = p(L, "txn_prefix", i=i) if len(c.transactions) > 1 else ""
            parts.append(p(L, "txn_line", prefix=prefix, amt=amt, when=when, utr=utr))
        prim = c.suspect.primary()
        if prim:
            kind, value = prim
            parts.append(p(L, "money_to", v=speak_identifier(kind, value, L) if spoken else value))
        parts.append(p(L, "your_bank", bank=c.victim_bank or unk))
        return " ".join(parts)

    # ---------------------------------------------------------------- step
    def step(self, utterance: str, meta: Optional[Dict] = None) -> Reply:
        self.turns += 1
        utterance = (utterance or "").strip()
        self._log("caller", utterance, state=self.state, **(meta or {}))
        events: List[Dict] = []
        pre: List[str] = []

        if self.state == "done":
            return self._say(p(self.lang, "done", case_id_spoken=speak_case_id(self.case.id, self.lang)),
                             events, done=True)

        if self.state == "open" and not self.lang_locked and utterance:
            self.case.lang = X.detect_language(utterance)

        if not utterance:
            return self._say(p(self.lang, "sorry") + " " + self.last_prompt, events)

        if X.is_repeat(utterance) and not N.spoken_digit_runs(utterance):
            return self._say(self.last_prompt, events)

        expecting = self.state if self.state in ("amount", "time", "utr", "suspect", "bank", "mode") else None
        ex = X.extract_all(utterance, expecting=expecting, now=self._now())

        # live threat interrupt (any turn)
        if ex.threat.live and not self.case.live_threat:
            self.case.live_threat = True
            self.case.remote_app = self.case.remote_app or ex.threat.remote_app
            self.case.threat_cues = sorted(set(self.case.threat_cues) | set(ex.threat.cues))
            self.case.threat_checked = True
            if self.case.fraud_type == "other" and ex.threat.remote_app:
                self._set_fraud("remote_access", ex.threat.cues)
            events.append({"type": "live_threat", "cues": ex.threat.cues})

        self._last_utterance = utterance
        handler = getattr(self, f"_on_{self.state}")
        msg = handler(utterance, ex, events)
        if msg:
            pre.append(msg)

        if self.case.live_threat and not getattr(self, "_threat_announced", False):
            pre.insert(0, self._threat_message())
            self._threat_announced = True

        if self.state == "done":
            return self._say(" ".join(pre), events, done=True)

        nxt = self.fixing_target() or self._next_state()
        self.state = nxt
        if getattr(self, "_suppress", False):
            self._suppress = False
            return self._say(" ".join(pre), events)
        prompt = self._prompt_for(nxt)
        return self._say(" ".join(pre + [prompt]), events)

    def fixing_target(self) -> Optional[str]:
        if self.fixing:
            target = self.fixing
            self.fixing = None
            return target
        return None

    def _say(self, text: str, events: List[Dict], done: bool = False) -> Reply:
        text = " ".join(text.split())
        self.last_prompt = text
        self._log("agent", text, state=self.state)
        return Reply(text, self.state, done, events)

    # ------------------------------------------------------------ handlers
    def _on_open(self, u, ex, events):
        self.case.narrative = (self.case.narrative + " " + u).strip()
        self._absorb(ex, None)
        return ""

    def _on_threat_check(self, u, ex, events):
        self.case.threat_checked = True
        yn = X.yes_no(u)
        self._absorb(ex, None)
        if yn is True and not self.case.live_threat:
            self.case.live_threat = True
            events.append({"type": "live_threat", "cues": ["caller confirmed still on call"]})
            return ""
        if yn is False:
            return p(self.lang, "no_threat")
        return ""

    def _retry_or_unknown(self, slot: str, retry_key: str, mark) -> str:
        if self._bump(slot) > MAX_RETRIES:
            mark()
            return p(self.lang, "ack")
        self.fixing = slot
        self._suppress = True
        return p(self.lang, retry_key)

    def _on_amount(self, u, ex, events):
        if ex.amount is not None and V.check_amount(ex.amount).ok:
            self._set_amount(ex.amount)
            self._absorb(ex, "amount")
            return p(self.lang, "ack")
        if X.is_dont_know(u):
            self.txn.amount_status = "unknown"
            self._absorb(ex, "amount")
            return p(self.lang, "ack")
        self._absorb(ex, "amount")
        v = self._llm_value("amount", u, events)
        if v is not None:
            self._set_amount(v)
            return p(self.lang, "ack")
        return self._retry_or_unknown("amount", "amount_retry",
                                      lambda: setattr(self.txn, "amount_status", "unknown"))

    def _golden_line(self) -> str:
        m = self.txn.minutes_ago
        if m is None:
            return ""
        return p(self.lang, "golden_ok" if m <= 120 else "golden_late")

    def _on_time(self, u, ex, events):
        if ex.minutes_ago is not None:
            self._set_time(ex.minutes_ago)
            self._absorb(ex, "time")
            return self._golden_line()
        if X.is_dont_know(u):
            self.txn.time_status = "unknown"
            self._absorb(ex, "time")
            return p(self.lang, "ack")
        self._absorb(ex, "time")
        v = self._llm_value("time", u, events)
        if v is not None:
            self._set_time(v)
            return self._golden_line()
        return self._retry_or_unknown("time", "time_retry",
                                      lambda: setattr(self.txn, "time_status", "unknown"))

    def _on_mode(self, u, ex, events):
        mode = ex.mode or X.detect_payment_mode(u)
        self._absorb(ex, "mode")
        if not mode:
            mode = self._llm_value("mode", u, events)
        if mode:
            self._set_mode(mode)
        else:
            self.txn.mode = None
            self.txn.mode_status = "unknown"
        return p(self.lang, "ack")

    def _on_utr(self, u, ex, events):
        t = self.txn
        t.utr_attempts += 1
        if ex.utr:
            t.utr = ex.utr
            if t.utr_first_heard is None:
                t.utr_first_heard = ex.utr
            t.utr_status = "pending_confirm"
            return ""
        if X.is_dont_know(u):
            t.utr_status = "unknown"
            return p(self.lang, "utr_unknown")
        if ex.utr_partial:
            if t.utr_first_heard is None:
                t.utr_first_heard = ex.utr_partial
            events.append({"type": "validator_reprompt", "field": "utr", "heard_digits": len(ex.utr_partial)})
            if self._bump("utr") > MAX_RETRIES:
                t.utr_status = "unknown"
                return p(self.lang, "utr_unknown")
            self.fixing = "utr"
            self._suppress = True
            return p(self.lang, "utr_partial", n=len(ex.utr_partial))
        v = self._llm_value("utr", u, events)
        if v:
            t.utr = v
            t.utr_first_heard = t.utr_first_heard or v
            t.utr_status = "pending_confirm"
            return ""
        return self._retry_or_unknown("utr", "utr_retry", lambda: setattr(t, "utr_status", "unknown"))

    def _on_utr_confirm(self, u, ex, events):
        t = self.txn
        yn = X.yes_no(u)
        _u, _part = X._utr_from(u)
        new_digits = _u or _part or ""
        if yn is True and not (len(new_digits) == 12 and new_digits != t.utr):
            t.utr_status = "confirmed"
            return p(self.lang, "ack")
        # caller corrected inline: "nahi, 4123 5678 9013"
        chk = V.check_utr(new_digits)
        if chk.ok and chk.value != t.utr:
            t.utr = chk.value
            t.utr_status = "pending_confirm"
            events.append({"type": "readback_correction", "field": "utr"})
            return ""
        if yn is False:
            t.utr = None
            t.utr_status = "missing"
            events.append({"type": "readback_correction", "field": "utr"})
            if self._bump("utr_confirm") > MAX_RETRIES:
                t.utr_status = "unknown"
                return p(self.lang, "ack")
            self.fixing = "utr"
            return p(self.lang, "sorry")
        return ""

    def _on_suspect(self, u, ex, events):
        s = ex.suspect if ex.suspect.any() else X.extract_suspect(u, allow_12_digit_account=True)
        if not s.any() and not X.is_dont_know(u):
            s = self._llm_value("suspect", u, events) or s
        cs = self.case.suspect
        if s.any():
            cs.upi, cs.mobile, cs.account = s.upi or cs.upi, s.mobile or cs.mobile, s.account or cs.account
            cs.spell_check = bool(s.upi) and X.upi_needs_spelling(u)
            if cs.first_heard is None:
                k, v = cs.primary()
                cs.first_heard = v
            cs.status = "pending_confirm"
            self._infer_mode()
            return ""
        if X.is_dont_know(u):
            cs.status = "unknown"
            return p(self.lang, "ack")
        return self._retry_or_unknown("suspect", "suspect_retry", lambda: setattr(cs, "status", "unknown"))

    def _on_suspect_confirm(self, u, ex, events):
        cs = self.case.suspect
        yn = X.yes_no(u)
        s = X.extract_suspect(u, allow_12_digit_account=True)
        if yn is True and not s.any():
            cs.status = "confirmed"
            return p(self.lang, "ack")
        if s.any() and s.identifiers() != cs.identifiers():
            cs.upi, cs.mobile, cs.account = s.upi, s.mobile, s.account
            cs.status = "pending_confirm"
            events.append({"type": "readback_correction", "field": "suspect"})
            return ""
        if yn is False and cs.upi and (cs.spell_check or cs.spelled_by_caller) and self.retries.get("spell", 0) < MAX_RETRIES:
            # the handle is fine, the Latin spelling of the name is the doubt -> ask for letters
            events.append({"type": "readback_correction", "field": "suspect"})
            self.fixing = "suspect_spell"
            return ""
        if yn is False:
            cs.upi = cs.mobile = cs.account = None
            cs.status = "missing"
            events.append({"type": "readback_correction", "field": "suspect"})
            if self._bump("suspect_confirm") > MAX_RETRIES:
                cs.status = "unknown"
                return p(self.lang, "ack")
            self.fixing = "suspect"
            return p(self.lang, "sorry")
        return ""

    def _on_suspect_spell(self, u, ex, events):
        from .translit import spelled_word
        cs = self.case.suspect
        self._bump("spell")
        name = spelled_word(u.replace(",", " ").split())
        if name and cs.upi:
            handle = cs.upi.split("@", 1)[1]
            cs.upi = f"{name}@{handle}"
            cs.spell_check = False
            cs.spelled_by_caller = True
            cs.status = "pending_confirm"
            events.append({"type": "spelled_upi", "value": cs.upi})
            return ""
        if self.retries["spell"] >= MAX_RETRIES:
            cs.status = "confirmed"   # keep the phonetic version; the officer sees spell_check=True
            return p(self.lang, "ack")
        self.fixing = "suspect_spell"
        return p(self.lang, "sorry")

    def _on_bank(self, u, ex, events):
        bank = ex.bank or X.detect_bank(u)
        if X.is_dont_know(u) and not bank:
            self.case.bank_status = "unknown"
            return p(self.lang, "ack")
        if not bank:
            bank = self._llm_value("bank", u, events)
        if bank:
            self._set_bank(bank)
            return p(self.lang, "ack")
        return self._retry_or_unknown("bank", "bank_retry", lambda: setattr(self.case, "bank_status", "unknown"))

    def _on_more_txn(self, u, ex, events):
        self._more_asked = len(self.case.transactions)
        yn = X.yes_no(u)
        if (yn is True or ex.amount) and len(self.case.transactions) < MAX_TXNS:
            self.case.transactions.append(Transaction())
            self.retries = {}
            if ex.amount:
                self._set_amount(ex.amount)
            if ex.minutes_ago is not None:
                self._set_time(ex.minutes_ago)
            if ex.utr:
                self.txn.utr, self.txn.utr_first_heard, self.txn.utr_status = ex.utr, ex.utr, "pending_confirm"
            # same fraudster and bank usually; mode carries over
            prev = self.case.transactions[-2]
            if prev.mode:
                self._set_mode(prev.mode)
            events.append({"type": "new_transaction", "index": len(self.case.transactions)})
            return p(self.lang, "ack")
        return ""

    def _on_summary(self, u, ex, events):
        yn = X.yes_no(u)
        slots = X.mentioned_slots(u)
        if yn is True and not slots:
            self._file()
            events.append({"type": "case_filed", "case_id": self.case.id})
            return p(self.lang, "done", case_id_spoken=speak_case_id(self.case.id, self.lang))
        if slots:
            return self._start_fix(slots[0], u, ex, events)
        if yn is False:
            self.state = "fix_which"
            self.fixing = "fix_which"
            return ""
        return ""

    def _on_fix_which(self, u, ex, events):
        slots = X.mentioned_slots(u)
        if slots:
            return self._start_fix(slots[0], u, ex, events)
        if X.yes_no(u) is True:
            self._file()
            events.append({"type": "case_filed", "case_id": self.case.id})
            return p(self.lang, "done", case_id_spoken=speak_case_id(self.case.id, self.lang))
        self.fixing = "fix_which"
        return p(self.lang, "sorry")

    def _start_fix(self, slot: str, u, ex, events) -> str:
        """Reset the slot; if the new value is already in this utterance, take it."""
        t = self.txn
        events.append({"type": "summary_correction", "field": slot})
        if slot == "amount":
            amt = N.parse_amount(u, expecting_amount=True)
            t.amount_status = "missing"
            if amt:
                self._set_amount(amt)
                return p(self.lang, "ack")
            self.fixing = "amount"
        elif slot == "time":
            m = X.parse_minutes_ago(u, self._now())
            t.time_status = "missing"
            if m is not None:
                self._set_time(m)
                return p(self.lang, "ack")
            self.fixing = "time"
        elif slot == "utr":
            _u, _part = X._utr_from(u)
            d = _u or _part or ""
            if V.check_utr(d).ok:
                t.utr, t.utr_status = d, "pending_confirm"
                return ""
            t.utr, t.utr_status = None, "missing"
            self.fixing = "utr"
        elif slot == "suspect":
            s = X.extract_suspect(u, allow_12_digit_account=True)
            cs = self.case.suspect
            cs.upi = cs.mobile = cs.account = None
            cs.status = "missing"
            if s.any():
                cs.upi, cs.mobile, cs.account = s.upi, s.mobile, s.account
                cs.status = "pending_confirm"
                return ""
            self.fixing = "suspect"
        elif slot == "bank":
            b = X.detect_bank(u)
            self.case.bank_status = "missing"
            if b:
                self._set_bank(b)
                return p(self.lang, "ack")
            self.fixing = "bank"
        elif slot == "mode":
            t.mode_status = "missing"
            self.fixing = "mode"
        return p(self.lang, "ack")

    def _file(self):
        for t in self.case.transactions:
            if t.mode_status != "captured" and self.case.suspect.upi:
                t.mode, t.mode_status = "UPI", "captured"
        self.case.status = "filed"
        self.case.filed_at = self._now().isoformat(timespec="seconds")
        self.state = "done"
