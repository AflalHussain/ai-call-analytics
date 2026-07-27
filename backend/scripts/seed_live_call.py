#!/usr/bin/env python3
"""POST a single call to the running API — the demo-day safety net.

The live moment depends on the voice agent emitting a DATA_CONTRACT.md record
to /ingest/call. If that wiring is not ready, this script drives the *same*
code path from a laptop, so the live segment of the demo works either way.

    python scripts/seed_live_call.py                       # a good-news call
    python scripts/seed_live_call.py --scenario angry      # escalated, churn risk
    python scripts/seed_live_call.py --scenario outage     # feeds the Gampaha alert
    python scripts/seed_live_call.py --scenario tamil      # Tamil-language call
"""

from __future__ import annotations

import argparse
import hashlib
import random
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

TZ = ZoneInfo("Asia/Colombo")

SCENARIOS = {
    "happy": {
        "intent": "data_package",
        "district": "Colombo",
        "language_primary": "si",
        "language_mix": ["si", "en"],
        "handled_by": "ai",
        "resolved": True,
        "duration_sec": 128,
        "sentiment_start": 0.05,
        "sentiment_end": 0.78,
        "csat_predicted": 5,
        "topics": ["data", "package", "activation"],
        "upsell_opportunity": "postpaid_migration",
        "churn_risk": False,
        "churn_signals": [],
        "escalation_reason": None,
        "actions_taken": [
            {"action": "lookup_account", "status": "ok"},
            {"action": "list_packages", "status": "ok"},
            {"action": "activate_package", "status": "ok"},
        ],
        "affected_number": None,   # account-level — no single line
        "callback_number": None,   # resolved live — no callback needed
        "caller_number": "0716620145",   # incoming CLI
        "summary": "Customer activated the 25GB monthly data package. Confirmed by SMS.",
        "unanswered_questions": [],
    },
    "angry": {
        "intent": "complaint_followup",
        "district": "Kandy",
        "language_primary": "si",
        "language_mix": ["si", "en"],
        "handled_by": "escalated",
        "resolved": False,
        "duration_sec": 264,
        "sentiment_start": -0.74,
        "sentiment_end": -0.31,
        "csat_predicted": 2,
        "topics": ["complaint", "ticket_followup"],
        "upsell_opportunity": None,
        "churn_risk": True,
        "churn_signals": ["mentioned_competitor", "repeat_unresolved_issue"],
        "escalation_reason": "high_frustration",
        "actions_taken": [
            {"action": "lookup_ticket", "status": "ok"},
            {"action": "fetch_ticket_status", "status": "ok"},
        ],
        "affected_number": "0812234871",   # Kandy landline the ticket is about
        "callback_number": "0771234567",   # caller asked to be called back
        "caller_number": "0771234567",     # calling from their mobile (same as callback)
        "summary": "Customer chasing a fault ticket open for 5 days. Escalated to a retention agent.",
        "unanswered_questions": [
            "What compensation applies for an outage lasting over 24 hours?"
        ],
    },
    "outage": {
        "intent": "broadband_fault",
        "district": "Gampaha",
        "language_primary": "si",
        "language_mix": ["si"],
        "handled_by": "ai",
        "resolved": True,
        "duration_sec": 187,
        "sentiment_start": -0.68,
        "sentiment_end": -0.05,
        "csat_predicted": 3,
        "topics": ["outage", "no_connection", "fibre"],
        "upsell_opportunity": None,
        "churn_risk": False,
        "churn_signals": [],
        "escalation_reason": None,
        "actions_taken": [
            {"action": "lookup_account", "status": "ok"},
            {"action": "run_line_test", "status": "ok"},
            {"action": "raise_fault_ticket", "status": "ok", "ref": "FLT-902817"},
        ],
        "affected_number": "0332248193",   # Gampaha landline — the affected line
        "callback_number": "0762889104",   # caller wants an update once restored
        "caller_number": "0761100338",     # calling from a mobile (landline is down)
        "summary": "Another Gampaha broadband outage report. Linked to the existing area incident.",
        "unanswered_questions": [],
    },
    "tamil": {
        "intent": "bill_inquiry",
        "district": "Jaffna",
        "language_primary": "ta",
        "language_mix": ["ta", "en"],
        "handled_by": "ai",
        "resolved": True,
        "duration_sec": 141,
        "sentiment_start": -0.22,
        "sentiment_end": 0.61,
        "csat_predicted": 5,
        "topics": ["billing", "charges"],
        "upsell_opportunity": None,
        "churn_risk": False,
        "churn_signals": [],
        "escalation_reason": None,
        "actions_taken": [
            {"action": "lookup_account", "status": "ok"},
            {"action": "fetch_bill", "status": "ok"},
            {"action": "explain_charges", "status": "ok"},
        ],
        "affected_number": None,   # account-level bill query
        "callback_number": None,   # resolved live — no callback needed
        "caller_number": "0212234517",   # calling from a Jaffna landline
        "summary": "Customer queried a roaming charge on this month's bill. Explained in Tamil; customer satisfied.",
        "unanswered_questions": [],
    },
}


def build(scenario: str) -> dict:
    s = dict(SCENARIOS[scenario])
    now = datetime.now(TZ).replace(microsecond=0)
    duration = s.pop("duration_sec")
    msisdn = f"94{random.randint(700000000, 799999999)}"

    return {
        "call_id": f"call_live_{uuid.uuid4().hex[:16]}",
        "started_at": (now - timedelta(seconds=duration)).isoformat(),
        "ended_at": now.isoformat(),
        "duration_sec": duration,
        "ai_handling_sec": duration if s["handled_by"] == "ai" else int(duration * 0.55),
        "queue_wait_sec": 1,
        "caller_hash": "sha256:" + hashlib.sha256(msisdn.encode()).hexdigest()[:32],
        "customer_segment": "postpaid",
        "channel": "voice_inbound",
        "sub_intent": None,
        "interruptions": 1,
        "silence_ratio": 0.06,
        "enrichment_model": "claude-opus-4-8",
        "enrichment_confidence": 0.94,
        "schema_version": "0.1",
        **s,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scenario", choices=sorted(SCENARIOS), default="happy")
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--count", type=int, default=1)
    args = ap.parse_args()

    for _ in range(args.count):
        payload = build(args.scenario)
        r = httpx.post(f"{args.api}/ingest/call", json=payload, timeout=15)
        r.raise_for_status()
        print(f"{payload['call_id']}  {args.scenario:7s} -> {r.status_code} {r.json()}")


if __name__ == "__main__":
    main()
