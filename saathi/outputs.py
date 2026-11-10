"""Actions the agent takes when a complaint is filed (Sentinel-style: act, don't just talk).

* a portal-ready complaint draft, structured like the National Cybercrime
  Reporting Portal's financial-fraud form
* a debit-freeze request draft addressed to the victim bank's nodal officer
* an SMS acknowledgement for the caller

All three are drafts for an authorised officer. Nothing is sent to any real
bank or government system by this prototype.
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from . import numbers as N
from .models import Case
from .validators import mask


def ncrp_draft(case: Case) -> Dict:
    txns = []
    for i, t in enumerate(case.transactions, 1):
        txns.append({
            "sr_no": i,
            "amount_inr": t.amount,
            "transaction_datetime": t.txn_time,
            "reference_utr": t.utr,
            "utr_verified_by_readback": t.utr_status == "confirmed",
            "payment_mode": t.mode,
            "victim_bank": case.victim_bank,
        })
    return {
        "draft_type": "Online Financial Fraud complaint (draft for officer review)",
        "synthetic_data": case.synthetic,
        "complaint_ref": case.id,
        "category": case.ncrp_category,
        "sub_category": case.ncrp_subcategory,
        "fraud_pattern": case.fraud_label,
        "reported_at": case.filed_at or case.call_started_at,
        "total_amount_inr": case.total_amount,
        "transactions": txns,
        "suspect": {
            "upi_id": case.suspect.upi,
            "mobile": case.suspect.mobile,
            "bank_account": case.suspect.account,
            "verified_by_readback": case.suspect.status == "confirmed",
        },
        "incident_description": case.summary or case.narrative,
        "live_threat_at_reporting": case.live_threat,
        "language_of_call": case.lang,
    }


def bank_freeze_request(case: Case) -> str:
    bank = case.victim_bank or "[Victim bank]"
    lines: List[str] = [
        "DRAFT - for verification and dispatch by an authorised officer",
        "",
        f"To: The Nodal Officer, {bank}",
        f"Subject: Request to hold/freeze proceeds of reported cyber financial fraud - Ref {case.id}",
        "",
        "Sir/Madam,",
        "",
        "A cyber financial fraud has been reported on helpline 1930. You are requested to trace the",
        "following debit(s) and place an immediate hold on the beneficiary account / onward transfers,",
        "as per the cyber-fraud reporting procedure.",
        "",
        "Transactions:",
    ]
    for i, t in enumerate(case.transactions, 1):
        amt = f"Rs {N.format_inr(t.amount)}" if t.amount else "amount not known"
        when = t.txn_time.replace("T", " ") if t.txn_time else "time not known"
        utr = t.utr or "UTR not known"
        lines.append(f"  {i}. {amt} | {when} | UTR/RRN: {utr} | mode: {t.mode or 'not known'}")
    lines += ["", "Beneficiary (suspect) identifiers:"]
    ids = case.suspect.identifiers()
    if ids:
        for kind, value in ids:
            lines.append(f"  - {kind.upper()}: {value}")
    else:
        lines.append("  - not provided by complainant")
    lines += [
        "",
        f"Fraud pattern: {case.fraud_label}",
        f"Total reported: Rs {N.format_inr(case.total_amount)}" if case.total_amount else "Total reported: not known",
        "",
        "Regards,",
        "Duty Officer, Cyber Helpline 1930",
    ]
    return "\n".join(lines)


def sms_ack(case: Case) -> str:
    t = case.transactions[0]
    amt = f"Rs {N.format_inr(case.total_amount)}" if case.total_amount else ""
    utr = f", UTR {mask(t.utr)}" if t.utr else ""
    if case.lang == "hi":
        return (f"1930 साथी: आपकी शिकायत {case.id} दर्ज। {amt}{utr}. "
                "बैंक हेल्पलाइन पर UPI/कार्ड ब्लॉक करवाएं और cybercrime.gov.in पर शिकायत पूरी करें। "
                "OTP/PIN किसी को न बताएं।")
    if case.lang == "pa":
        return (f"1930 ਸਾਥੀ: ਤੁਹਾਡੀ ਸ਼ਿਕਾਇਤ {case.id} ਦਰਜ। {amt}{utr}. "
                "ਬੈਂਕ ਹੈਲਪਲਾਈਨ ਤੋਂ UPI/ਕਾਰਡ ਬਲਾਕ ਕਰਵਾਓ ਤੇ cybercrime.gov.in ਉੱਤੇ ਸ਼ਿਕਾਇਤ ਪੂਰੀ ਕਰੋ। "
                "OTP/PIN ਕਿਸੇ ਨੂੰ ਨਾ ਦੱਸੋ।")
    if case.lang == "ta":
        return (f"1930 சாத்தி: உங்க புகார் {case.id} பதிவு. {amt}{utr}. "
                "பேங்க் ஹெல்ப்லைன் மூலம் UPI/கார்டை பிளாக் பண்ணுங்க, cybercrime.gov.in-ல் புகாரை முடிங்க. "
                "OTP/PIN யாருக்கும் சொல்லாதீங்க.")
    return (f"1930 Saathi: complaint {case.id} registered. {amt}{utr}. Block UPI/cards via your bank "
            "helpline and complete the complaint on cybercrime.gov.in. Never share OTP/PIN.")


def rule_summary(case: Case) -> str:
    parts = [case.fraud_label + "."]
    if case.total_amount:
        parts.append(f"Lost Rs {N.format_inr(case.total_amount)} in {len(case.transactions)} transaction(s).")
    prim = case.suspect.primary()
    if prim:
        parts.append(f"Beneficiary {prim[0]} {prim[1]}.")
    if case.live_threat:
        parts.append("Scam was still in progress during the call.")
    return " ".join(parts)
