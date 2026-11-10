from datetime import datetime, timedelta

from saathi import clusters as C
from saathi import outputs as O
from saathi import priority as P
from saathi.demo import seed_cases
from saathi.models import Case, SuspectInfo, Transaction
from saathi.store import Store

NOW = datetime(2026, 11, 6, 13, 0)


def make(amount, minutes, upi=None, mobile=None, threat=False):
    c = Case()
    c.transactions = [Transaction(amount=amount, minutes_ago=minutes,
                                  txn_time=(NOW - timedelta(minutes=minutes)).isoformat(), utr="412356789012")]
    c.suspect = SuspectInfo(upi=upi, mobile=mobile)
    c.live_threat = threat
    return c


def test_fresher_and_live_threat_rank_higher():
    fresh = P.score(make(10000, 15), now=NOW)["score"]
    old = P.score(make(10000, 600), now=NOW)["score"]
    threat = P.score(make(10000, 15, threat=True), now=NOW)["score"]
    assert threat > fresh > old


def test_golden_remaining():
    assert P.score(make(1000, 30), now=NOW)["golden_remaining_min"] == 90.0


def test_rings_union_find():
    a = make(1000, 10, upi="mule@ybl")
    b = make(2000, 10, upi="MULE@ybl", mobile="9999900001")
    c = make(3000, 10, mobile="9999900001")
    d = make(4000, 10, upi="other@ybl")
    clusters = C.build_clusters([a, b, c, d])
    ring = clusters[0]
    assert ring["is_ring"] and ring["size"] == 3 and ring["total_amount"] == 6000
    assert not clusters[1]["is_ring"]


def test_demo_seed_produces_ring_and_drafts():
    s = Store()
    ids = seed_cases(s)
    assert all(s.cases[i].status == "filed" for i in ids)
    rings = [c for c in s.clusters() if c["is_ring"]]
    assert rings and rings[0]["size"] == 3
    d = s.case_detail(ids[0])
    assert "Nodal Officer" in d["drafts"]["bank_freeze"]
    assert d["drafts"]["ncrp"]["category"] == "Online Financial Fraud"
    assert "1930" in d["drafts"]["sms"]


def test_sms_masks_utr():
    c = make(45000, 10)
    assert "********9012" in O.sms_ack(c)


def test_same_utr_is_duplicate_not_ring():
    """The same debit reported twice (re-call) must not look like a 2-victim ring."""
    a = make(200000, 30, mobile="9999900001")
    b = make(200000, 30, mobile="9999900001")
    for c in (a, b):
        c.transactions[0].utr_status = "confirmed"
    b.call_started_at = "2099-01-01T00:00:00"
    clusters = C.build_clusters([a, b])
    assert len(clusters) == 1
    cl = clusters[0]
    assert not cl["is_ring"] and cl["size"] == 1 and cl["reports"] == 2
    assert cl["duplicates"] == {b.id: a.id}
    assert cl["total_amount"] == 200000          # counted once
    # a genuine second victim (different UTR) to the same account is a ring
    c = make(50000, 10, mobile="9999900001")
    c.transactions[0].utr, c.transactions[0].utr_status = "998877665544", "confirmed"
    ring = C.build_clusters([a, b, c])[0]
    assert ring["is_ring"] and ring["size"] == 2 and ring["reports"] == 3 and ring["total_amount"] == 250000


def test_queue_flags_duplicate_and_ranks_it_lower():
    s = Store()
    ids = seed_cases(s)
    first = s.cases[ids[0]]
    from saathi.demo import SCRIPTS
    from saathi.demo import run_script
    dup_id = run_script(s, "re-call", SCRIPTS[0][1])
    q = s.queue_view()
    row = next(r for r in q if r["id"] == dup_id)
    assert row["duplicate_of"] == first.id
    assert q[-1]["id"] == dup_id or all(r["duplicate_of"] for r in q[q.index(row):])
    assert s.case_detail(dup_id)["duplicate_of"] == first.id
