"""Case data model."""
from __future__ import annotations

import secrets
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional


def new_case_id() -> str:
    return "S1930-" + str(secrets.randbelow(900000) + 100000)


@dataclass
class Transaction:
    amount: Optional[int] = None
    amount_status: str = "missing"        # missing | captured | unknown
    minutes_ago: Optional[int] = None
    time_status: str = "missing"
    txn_time: Optional[str] = None        # ISO, derived from call time - minutes_ago
    mode: Optional[str] = None
    mode_status: str = "missing"
    utr: Optional[str] = None
    utr_status: str = "missing"           # missing | pending_confirm | confirmed | unknown
    utr_first_heard: Optional[str] = None  # what we heard before read-back (for evaluation)
    utr_attempts: int = 0


@dataclass
class SuspectInfo:
    upi: Optional[str] = None
    mobile: Optional[str] = None
    account: Optional[str] = None
    status: str = "missing"               # missing | pending_confirm | confirmed | unknown
    first_heard: Optional[str] = None
    spell_check: bool = False             # UPI name came from Indic-script sounds -> read back letters
    spelled_by_caller: bool = False

    def identifiers(self) -> List[tuple]:
        out = []
        if self.upi:
            out.append(("upi", self.upi))
        if self.mobile:
            out.append(("mobile", self.mobile))
        if self.account:
            out.append(("account", self.account))
        return out

    def primary(self) -> Optional[tuple]:
        ids = self.identifiers()
        return ids[0] if ids else None


@dataclass
class Turn:
    role: str            # caller | agent | system
    text: str
    ts: str
    meta: Dict = field(default_factory=dict)


@dataclass
class Case:
    id: str = field(default_factory=new_case_id)
    call_started_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    filed_at: Optional[str] = None
    lang: str = "hi"
    synthetic: bool = True
    caller_label: str = "Synthetic caller"
    fraud_type: str = "other"
    fraud_label: str = "Other online financial fraud"
    ncrp_category: str = "Online Financial Fraud"
    ncrp_subcategory: str = "Other"
    fraud_cues: List[str] = field(default_factory=list)
    narrative: str = ""
    transactions: List[Transaction] = field(default_factory=lambda: [Transaction()])
    suspect: SuspectInfo = field(default_factory=SuspectInfo)
    victim_bank: Optional[str] = None
    bank_status: str = "missing"
    live_threat: bool = False
    remote_app: bool = False
    threat_cues: List[str] = field(default_factory=list)
    threat_checked: bool = False
    status: str = "intake"                # intake | filed | freeze_requested | closed
    summary: str = ""
    summary_source: str = "rules"
    transcript: List[Turn] = field(default_factory=list)
    priority: float = 0.0
    cluster_id: Optional[str] = None
    officer_notes: List[Dict] = field(default_factory=list)
    field_sources: Dict[str, str] = field(default_factory=dict)   # slot -> "rules" | "llm"
    caller_number: Optional[str] = None     # from telephony caller ID or entered in the simulator
    caller_number_source: str = "none"      # none | caller_id | entered
    channel: str = "web"                    # web | twilio | exotel

    @property
    def total_amount(self) -> int:
        return sum(t.amount or 0 for t in self.transactions)

    def earliest_txn_time(self) -> Optional[datetime]:
        times = [datetime.fromisoformat(t.txn_time) for t in self.transactions if t.txn_time]
        return min(times) if times else None

    def golden_deadline(self, window_min: int = 120) -> Optional[datetime]:
        """Golden window measured from the most recent transaction (freshest money is most recoverable)."""
        times = [datetime.fromisoformat(t.txn_time) for t in self.transactions if t.txn_time]
        if not times:
            return None
        return max(times) + timedelta(minutes=window_min)

    def to_dict(self) -> Dict:
        d = asdict(self)
        d["total_amount"] = self.total_amount
        gd = self.golden_deadline()
        d["golden_deadline"] = gd.isoformat(timespec="seconds") if gd else None
        return d
