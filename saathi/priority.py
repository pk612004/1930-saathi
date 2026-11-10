"""Golden-hour priority scoring for the officer queue.

Police across India describe the first one-to-two hours after a fraud as the
"golden hour": money still sitting in the first mule account can be frozen.
The queue therefore ranks complaints by how much recoverable money is still
inside that window, boosted when the scam is still in progress or when the
fraudster's identifier already appears in other complaints (a mule ring).
"""
from __future__ import annotations

import math
from datetime import datetime
from typing import Dict, Optional

from .models import Case

GOLDEN_WINDOW_MIN = 120


def minutes_since_latest_txn(case: Case, now: Optional[datetime] = None) -> Optional[float]:
    now = now or datetime.now()
    times = [datetime.fromisoformat(t.txn_time) for t in case.transactions if t.txn_time]
    if not times:
        return None
    return (now - max(times)).total_seconds() / 60


def golden_remaining_min(case: Case, now: Optional[datetime] = None) -> Optional[float]:
    m = minutes_since_latest_txn(case, now)
    if m is None:
        return None
    return GOLDEN_WINDOW_MIN - m


def score(case: Case, cluster_size: int = 1, now: Optional[datetime] = None) -> Dict:
    m = minutes_since_latest_txn(case, now)
    if m is None:
        window = 30.0           # unknown time: assume recent enough to look at quickly
        window_label = "time unknown"
    elif m <= 60:
        window, window_label = 100.0, "inside golden hour"
    elif m <= GOLDEN_WINDOW_MIN:
        window, window_label = 80.0, "golden window closing"
    elif m <= 24 * 60:
        window, window_label = 35.0, "same day"
    else:
        window, window_label = 10.0, "older than a day"

    amount = case.total_amount
    money = 8.0 * math.log10(amount + 1) if amount else 0.0
    actionable = 0.0
    if any(t.utr for t in case.transactions):
        actionable += 10.0
    if case.suspect.identifiers():
        actionable += 8.0
    threat = 25.0 if case.live_threat else 0.0
    ring = 12.0 * (cluster_size - 1) if cluster_size > 1 else 0.0
    total = round(window + money + actionable + threat + ring, 1)
    return {
        "score": total,
        "window": window_label,
        "minutes_since_txn": None if m is None else round(m, 1),
        "golden_remaining_min": None if m is None else round(GOLDEN_WINDOW_MIN - m, 1),
        "parts": {"window": window, "money": round(money, 1), "actionable": actionable,
                  "live_threat": threat, "mule_ring": ring},
    }
