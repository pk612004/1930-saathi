"""Mule-account ring detection across complaints.

Each complaint is linked to the fraudster identifiers it mentions (UPI ID,
mobile, account). Complaints that share any identifier are merged with a
union-find, so the officer sees "3 victims paid the same UPI ID in the last
hour" the moment the third call ends, instead of after a manual audit.
"""
from __future__ import annotations

from typing import Dict, Iterable, List

from .models import Case


class UnionFind:
    def __init__(self):
        self.parent: Dict[str, str] = {}

    def find(self, x: str) -> str:
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)


def _id_node(kind: str, value: str) -> str:
    return f"{kind}:{value.lower()}"


def _utrs(c: Case) -> set:
    return {t.utr for t in c.transactions if t.utr and t.utr_status == "confirmed"}


def find_duplicates(cases: Iterable[Case]) -> Dict[str, str]:
    """Complaints that share a confirmed UTR describe the same debit, so they are
    one victim reported twice (a re-call, or a relative calling again), not a ring.
    Returns {duplicate_case_id: earliest_case_id}."""
    # stable sort: same-second calls keep the order they reached the store
    cases = sorted(cases, key=lambda c: c.call_started_at or "")
    first_by_utr: Dict[str, str] = {}
    dup: Dict[str, str] = {}
    for c in cases:
        hit = next((first_by_utr[u] for u in _utrs(c) if u in first_by_utr), None)
        if hit:
            dup[c.id] = dup.get(hit, hit)
        for u in _utrs(c):
            first_by_utr.setdefault(u, dup.get(c.id, c.id))
    return dup


def build_clusters(cases: Iterable[Case]) -> List[Dict]:
    cases = list(cases)
    dups = find_duplicates(cases)
    cases = [c for c in cases if c.suspect.identifiers()]
    uf = UnionFind()
    for c in cases:
        node = f"case:{c.id}"
        uf.find(node)
        for kind, value in c.suspect.identifiers():
            uf.union(node, _id_node(kind, value))
    groups: Dict[str, Dict] = {}
    for c in cases:
        root = uf.find(f"case:{c.id}")
        g = groups.setdefault(root, {"cases": [], "identifiers": set(), "total_amount": 0, "amounts": {}, "live_threat": False})
        g["cases"].append(c.id)
        g["amounts"][c.id] = c.total_amount
        g["identifiers"].update(f"{k}:{v}" for k, v in c.suspect.identifiers())
        g["total_amount"] += c.total_amount
        g["live_threat"] = g["live_threat"] or c.live_threat
    out = []
    def victims(g):
        return len({dups.get(cid, cid) for cid in g["cases"]})
    for i, (root, g) in enumerate(sorted(groups.items(), key=lambda kv: (-victims(kv[1]), -len(kv[1]["cases"])))):
        v = victims(g)
        # money from duplicate reports is the same debit, count it once
        g["total_amount"] = sum(a for cid, a in g["amounts"].items() if cid not in dups)
        out.append({
            "cluster_id": f"RING-{i + 1:02d}",
            "cases": sorted(g["cases"]),
            "size": v,                      # distinct victims
            "reports": len(g["cases"]),     # complaints, incl. duplicates
            "duplicates": {cid: dups[cid] for cid in g["cases"] if cid in dups},
            "identifiers": sorted(g["identifiers"]),
            "total_amount": g["total_amount"],
            "is_ring": v >= 2,
            "live_threat": g["live_threat"],
        })
    return out


def cluster_of(case_id: str, clusters: List[Dict]) -> Dict:
    for cl in clusters:
        if case_id in cl["cases"]:
            return cl
    return {"cluster_id": None, "size": 1, "reports": 1, "cases": [case_id], "is_ring": False, "duplicates": {}}


def duplicate_of(case_id: str, clusters: List[Dict]):
    for cl in clusters:
        if case_id in cl.get("duplicates", {}):
            return cl["duplicates"][case_id]
    return None
