"""In-memory case store with JSON persistence and an event bus for the live console."""
from __future__ import annotations

import queue
import threading
from datetime import datetime
from typing import Dict, List, Optional

from . import clusters as C
from . import outputs as O
from . import priority as P
from .db import DB
from .security import CallerVerification
from .validators import mask
from .dialog import Dialog
from .models import Case, SuspectInfo, Transaction, Turn


class EventBus:
    def __init__(self):
        self._subs: List[queue.Queue] = []
        self._lock = threading.Lock()

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=200)
        with self._lock:
            self._subs.append(q)
        return q

    def unsubscribe(self, q: queue.Queue):
        with self._lock:
            if q in self._subs:
                self._subs.remove(q)

    def publish(self, event: Dict):
        with self._lock:
            subs = list(self._subs)
        for q in subs:
            try:
                q.put_nowait(event)
            except queue.Full:
                pass


def _case_from_dict(d: Dict) -> Case:
    d = dict(d)
    d.pop("total_amount", None)
    d.pop("golden_deadline", None)
    d["transactions"] = [Transaction(**t) for t in d.get("transactions", [])]
    d["suspect"] = SuspectInfo(**d.get("suspect", {}))
    d["transcript"] = [Turn(**t) for t in d.get("transcript", [])]
    return Case(**d)


class Store:
    def __init__(self, db_path: str = ":memory:"):
        self.db = DB(db_path)
        self.calls: Dict[str, Dialog] = {}
        self.cases: Dict[str, Case] = {}
        self.bus = EventBus()
        self.lock = threading.RLock()
        for d in self.db.load_cases():
            try:
                c = _case_from_dict(d)
                self.cases[c.id] = c
            except (TypeError, ValueError):
                pass

    def save(self, case: Optional[Case] = None):
        with self.lock:
            targets = [case] if case is not None else list(self.cases.values())
            for c in targets:
                self.db.upsert_case(c.to_dict())

    def delete(self, case_id: str):
        with self.lock:
            self.cases.pop(case_id, None)
            self.calls.pop(case_id, None)
        self.db.delete_case(case_id)

    # ---------------------------------------------------------------- calls
    def new_call(self, lang: Optional[str] = None, llm=None) -> Dialog:
        d = Dialog(lang=lang, llm=llm)
        with self.lock:
            self.calls[d.case.id] = d
            self.cases[d.case.id] = d.case
        return d

    def get_call(self, call_id: str) -> Optional[Dialog]:
        return self.calls.get(call_id)

    # ----------------------------------------------------------- analytics
    def clusters(self) -> List[Dict]:
        with self.lock:
            return C.build_clusters(self.cases.values())

    def rescore(self, now: Optional[datetime] = None):
        cl = self.clusters()
        with self.lock:
            for c in self.cases.values():
                info = C.cluster_of(c.id, cl)
                c.cluster_id = info.get("cluster_id") if info.get("is_ring") else None
                c.priority = P.score(c, info.get("size", 1), now)["score"]
        return cl

    def queue_view(self, now: Optional[datetime] = None) -> List[Dict]:
        cl = self.rescore(now)
        rows = []
        with self.lock:
            dups = C.find_duplicates(self.cases.values())
            for c in self.cases.values():
                info = C.cluster_of(c.id, cl)
                sc = P.score(c, info.get("size", 1), now)
                prim = c.suspect.primary()
                rows.append({
                    "id": c.id, "status": c.status, "fraud_label": c.fraud_label,
                    "fraud_type": c.fraud_type, "total_amount": c.total_amount,
                    "txn_count": len(c.transactions), "lang": c.lang,
                    "live_threat": c.live_threat, "priority": sc["score"], "window": sc["window"],
                    "golden_remaining_min": sc["golden_remaining_min"],
                    "minutes_since_txn": sc["minutes_since_txn"],
                    "golden_deadline": c.to_dict()["golden_deadline"],
                    "suspect": f"{prim[0]}:{prim[1]}" if prim else None,
                    "cluster_id": c.cluster_id, "cluster_size": info.get("size", 1),
                    "cluster_reports": info.get("reports", 1), "duplicate_of": dups.get(c.id),
                    "utr_confirmed": any(t.utr_status == "confirmed" for t in c.transactions),
                    "synthetic": c.synthetic, "filed_at": c.filed_at, "call_started_at": c.call_started_at,
                    "caller": mask(c.caller_number) if c.caller_number else None,
                    "verification": self.verification(c),
                    "channel": c.channel, "llm_fields": sorted(k for k, v in c.field_sources.items() if v == "llm"),
                    "txns": [{"amount": t.amount, "txn_time": t.txn_time} for t in c.transactions if t.amount],
                    "last_activity": c.transcript[-1].ts if c.transcript else c.call_started_at,
                    "live": self._live_view(c) if c.status == "intake" else None,
                })
        # a duplicate report of a debit already in the queue goes below fresh complaints
        rows.sort(key=lambda r: (r["status"] == "closed", r["duplicate_of"] is not None, -r["priority"]))
        return rows

    @staticmethod
    def _live_view(c: Case) -> Dict:
        """What a supervisor sees while the call is still going on."""
        tx = c.transactions[-1] if c.transactions else None
        prim = c.suspect.primary()
        known = c.fraud_type and c.fraud_type != "other"
        return {
            "fraud": c.fraud_label if known else None,
            "amount": tx.amount if tx else None,
            "minutes_ago": tx.minutes_ago if tx else None,
            "utr": tx.utr if tx else None, "utr_status": tx.utr_status if tx else "missing",
            "suspect": prim[1] if prim else None, "suspect_status": c.suspect.status,
            "bank": c.victim_bank,
            "threat": c.live_threat, "threat_checked": c.threat_checked,
            "turns": len([t for t in c.transcript if t.role == "caller"]),
            "last": [{"role": t.role, "text": t.text} for t in c.transcript[-2:]],
        }

    def verification(self, c: Case) -> str:
        v = CallerVerification(self.db).status(c.id)
        if v == "verified":
            return "otp_verified"
        if c.caller_number_source == "caller_id":
            return "caller_id" if v == "none" else f"caller_id+otp_{v}"
        return f"otp_{v}" if v != "none" else "unverified"

    def case_detail(self, case_id: str, now: Optional[datetime] = None) -> Optional[Dict]:
        c = self.cases.get(case_id)
        if not c:
            return None
        cl = self.clusters()
        info = C.cluster_of(c.id, cl)
        d = c.to_dict()
        d["score"] = P.score(c, info.get("size", 1), now)
        d["cluster"] = info
        d["duplicate_of"] = C.find_duplicates(self.cases.values()).get(c.id)
        d["verification"] = self.verification(c)
        d["audit"] = self.db.audit_for(case_id)
        d["drafts"] = {
            "ncrp": O.ncrp_draft(c),
            "bank_freeze": O.bank_freeze_request(c),
            "sms": O.sms_ack(c),
        }
        return d
