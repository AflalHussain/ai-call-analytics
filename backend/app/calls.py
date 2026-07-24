"""Call History explorer — list rows and per-call detail.

Kept separate from queries.py (which is pure aggregation): this module shapes
individual call rows and derives the human-readable outcome / sentiment bands and
the drawer's "key points" from the structured fields the contract already
carries. No new columns, no enrichment dependency — it runs on existing data.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from . import db
from .models import ESCALATION_LABELS, INTENT_LABELS, LANGUAGE_LABELS

# Sentiment band thresholds (on sentiment_end, -1..1).
POS = 0.2
NEG = -0.2


# --------------------------------------------------------------------------
# Derivations — display values computed from contract fields
# --------------------------------------------------------------------------

def customer_ref(caller_hash: str | None, call_id: str) -> str:
    """A stable per-caller reference, e.g. C-04217.

    Derived from the hashed MSISDN, so the SAME caller always maps to the SAME
    reference — repeat callers are visible in the list without ever exposing a
    real number. The raw MSISDN is never stored (see DATA_CONTRACT.md); this is a
    display label only.
    """
    src = caller_hash.split(":")[-1] if caller_hash else call_id
    n = int(hashlib.sha1(src.encode()).hexdigest()[:6], 16) % 100000
    return f"C-{n:05d}"


def short_id(call_id: str) -> str:
    """Compact call identifier for the drawer subtitle."""
    tail = call_id.split("_")[-1]
    return f"#{tail[-8:].upper()}"


def outcome_of(handled_by: str, resolved: bool) -> tuple[str, str]:
    """(display label, status token) for the outcome badge."""
    if handled_by == "abandoned":
        return "Abandoned", "critical"
    if handled_by == "escalated":
        return "Escalated", "warning"
    if handled_by == "transferred_ivr":
        return "Transferred", "neutral"
    if resolved:
        return "Resolved", "good"
    return "Unresolved", "warning"


def sentiment_band(end: float | None) -> tuple[str, str]:
    if end is None:
        return "—", "neutral"
    if end >= POS:
        return "Positive", "good"
    if end <= NEG:
        return "Negative", "critical"
    return "Neutral", "neutral"


_ACTION_PHRASE: dict[str, str] = {
    "lookup_account": "Account looked up",
    "fetch_bill": "Bill retrieved",
    "explain_charges": "Charges explained",
    "take_payment": "Payment taken",
    "send_receipt_sms": "Receipt sent by SMS",
    "apply_reload": "Reload applied",
    "send_confirmation_sms": "Confirmation SMS sent",
    "list_packages": "Packages compared",
    "activate_package": "Package activated",
    "fetch_balance": "Balance checked",
    "run_line_test": "Line test run",
    "raise_fault_ticket": "Fault ticket raised",
    "run_speed_diagnostic": "Speed diagnostic run",
    "remote_router_reboot": "Router rebooted remotely",
    "send_setup_guide": "Setup guide sent",
    "check_cell_status": "Cell tower status checked",
    "raise_coverage_ticket": "Coverage ticket raised",
    "refresh_set_top_box": "Set-top box refreshed",
    "verify_identity": "Identity verified",
    "order_sim_replacement": "SIM replacement ordered",
    "activate_roaming": "Roaming activated",
    "send_tariff_sms": "Tariff SMS sent",
    "schedule_package_change": "Package change scheduled",
    "check_coverage": "Coverage checked",
    "capture_lead": "Lead captured",
    "offer_retention": "Retention offer presented",
    "log_disconnection_request": "Disconnection request logged",
    "lookup_ticket": "Ticket looked up",
    "fetch_ticket_status": "Ticket status fetched",
    "fetch_outlet_info": "Outlet info provided",
}

_SIGNAL_LABEL: dict[str, str] = {
    "mentioned_competitor": "mentioned a competitor",
    "asked_about_disconnection": "asked about disconnection",
    "threatened_to_leave": "threatened to leave",
    "repeat_unresolved_issue": "repeat unresolved issue",
    "price_complaint": "price complaint",
    "asked_for_contract_end_date": "asked for contract end date",
}


def derive_key_points(row: dict[str, Any]) -> list[str]:
    """Build the drawer's key-point bullets from structured fields.

    The contract does not carry key_points; we reconstruct them from what
    enrichment already gives us (intent, actions, outcome, sentiment, open
    questions, churn signals). This keeps the drawer useful without adding a
    field the pipeline would have to populate.
    """
    points: list[str] = []

    reason = row.get("sub_intent") or INTENT_LABELS.get(row["intent"], row["intent"])
    points.append(f"Reason for call: {reason}")

    actions = row.get("actions_taken") or []
    # Defensive: tolerate legacy rows where actions_taken was double-encoded and
    # comes back as a JSON string rather than a list.
    if isinstance(actions, str):
        try:
            actions = json.loads(actions)
        except (ValueError, TypeError):
            actions = []
    verbs: list[str] = []
    for a in actions:
        name = a.get("action") if isinstance(a, dict) else None
        if not name:
            continue
        phrase = _ACTION_PHRASE.get(name, name.replace("_", " ").capitalize())
        ref = a.get("ref") if isinstance(a, dict) else None
        if ref:
            phrase = f"{phrase} ({ref})"
        if a.get("status") == "failed":
            phrase = f"{phrase} — failed"
        verbs.append(phrase)
    if verbs:
        # Cap at three so the bullet list stays scannable.
        points.append("Actions taken: " + ", ".join(verbs[:3]))

    handled_by = row["handled_by"]
    resolved = row["resolved"]
    if handled_by == "escalated":
        reason_lbl = ESCALATION_LABELS.get(row.get("escalation_reason"), "handed to a human")
        points.append(f"Outcome: escalated to a human — {reason_lbl.lower()}")
    elif handled_by == "abandoned":
        points.append("Outcome: caller hung up before the call completed")
    elif handled_by == "transferred_ivr":
        points.append("Outcome: transferred to the IVR menu")
    elif resolved:
        points.append("Outcome: resolved by the AI agent, no human needed")
    else:
        points.append("Outcome: handled by the AI agent but not fully resolved")

    s0, s1 = row.get("sentiment_start"), row.get("sentiment_end")
    if s0 is not None and s1 is not None:
        if s1 - s0 >= 0.25:
            points.append(f"Caller sentiment improved over the call ({s0:+.2f} → {s1:+.2f})")
        elif s1 - s0 <= -0.2:
            points.append(f"Caller sentiment worsened over the call ({s0:+.2f} → {s1:+.2f})")

    signals = row.get("churn_signals") or []
    if signals:
        readable = ", ".join(_SIGNAL_LABEL.get(s, s) for s in signals)
        points.append(f"Retention risk: {readable}")

    questions = row.get("unanswered_questions") or []
    if questions:
        points.append(f"Left unanswered: “{questions[0]}”")

    return points


# --------------------------------------------------------------------------
# Queries
# --------------------------------------------------------------------------

def _outcome_clause(value: str) -> str:
    return {
        "resolved": "handled_by = 'ai' AND resolved",
        "unresolved": "handled_by = 'ai' AND NOT resolved",
        "escalated": "handled_by = 'escalated'",
        "abandoned": "handled_by = 'abandoned'",
        "transferred": "handled_by = 'transferred_ivr'",
    }[value]


def _sentiment_clause(value: str) -> str:
    return {
        "positive": f"sentiment_end >= {POS}",
        "neutral": f"(sentiment_end IS NULL OR (sentiment_end > {NEG} AND sentiment_end < {POS}))",
        "negative": f"sentiment_end <= {NEG}",
    }[value]


async def list_calls(
    frm: datetime,
    to: datetime,
    *,
    search: str | None = None,
    outcome: str | None = None,
    sentiment: str | None = None,
    language: str | None = None,
    service: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    where = ["started_at >= $1", "started_at < $2"]
    params: list[Any] = [frm, to]

    def add(clause: str, value: Any) -> None:
        params.append(value)
        where.append(clause.replace("$$", f"${len(params)}"))

    if search:
        add("call_id ILIKE '%' || $$ || '%'", search)
    if language:
        add("language_primary = $$", language)
    if service:
        add("intent = $$", service)
    # Outcome / sentiment are closed enums — safe to inline the fixed clause.
    if outcome in ("resolved", "unresolved", "escalated", "abandoned", "transferred"):
        where.append(_outcome_clause(outcome))
    if sentiment in ("positive", "neutral", "negative"):
        where.append(_sentiment_clause(sentiment))

    where_sql = " AND ".join(where)

    rows_sql = f"""
        SELECT call_id, caller_hash, started_at, duration_sec, district,
               intent, sub_intent, language_primary, handled_by, resolved,
               escalation_reason, sentiment_start, sentiment_end, csat_predicted,
               churn_risk
        FROM calls
        WHERE {where_sql}
        ORDER BY started_at DESC
        LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}
    """
    count_sql = f"SELECT count(*)::int FROM calls WHERE {where_sql}"

    async with db.pool().acquire() as conn:
        total = await conn.fetchval(count_sql, *params)
        rows = await conn.fetch(rows_sql, *params, limit, offset)

    calls = []
    for r in rows:
        oc_label, oc_status = outcome_of(r["handled_by"], r["resolved"])
        se_label, se_status = sentiment_band(r["sentiment_end"])
        calls.append({
            "call_id": r["call_id"],
            "customer_ref": customer_ref(r["caller_hash"], r["call_id"]),
            "started_at": r["started_at"].isoformat(),
            "duration_sec": r["duration_sec"],
            "service": INTENT_LABELS.get(r["intent"], r["intent"]),
            "intent": r["intent"],
            "district": r["district"],
            "language": LANGUAGE_LABELS.get(r["language_primary"], r["language_primary"]),
            "language_code": r["language_primary"],
            "outcome": oc_label,
            "outcome_status": oc_status,
            "sentiment": se_label,
            "sentiment_status": se_status,
            "csat": r["csat_predicted"] if r["handled_by"] != "abandoned" else None,
            "churn_risk": r["churn_risk"],
        })

    return {"total": total, "calls": calls, "limit": limit, "offset": offset}


async def call_detail(call_id: str) -> dict[str, Any] | None:
    sql = """
        SELECT call_id, caller_hash, started_at, ended_at, duration_sec,
               ai_handling_sec, district, customer_segment,
               intent, sub_intent, topics, language_primary, language_mix,
               handled_by, resolved, escalation_reason, actions_taken,
               sentiment_start, sentiment_end, csat_predicted,
               churn_risk, churn_signals, upsell_opportunity,
               unanswered_questions, summary
        FROM calls WHERE call_id = $1
    """
    async with db.pool().acquire() as conn:
        r = await conn.fetchrow(sql, call_id)
    if r is None:
        return None

    row = dict(r)
    oc_label, oc_status = outcome_of(row["handled_by"], row["resolved"])
    se_label, se_status = sentiment_band(row["sentiment_end"])

    return {
        "call_id": row["call_id"],
        "customer_ref": customer_ref(row["caller_hash"], row["call_id"]),
        "short_id": short_id(row["call_id"]),
        "started_at": row["started_at"].isoformat(),
        "duration_sec": row["duration_sec"],
        "service": INTENT_LABELS.get(row["intent"], row["intent"]),
        "district": row["district"],
        "customer_segment": row["customer_segment"],
        "language": LANGUAGE_LABELS.get(row["language_primary"], row["language_primary"]),
        "languages": [LANGUAGE_LABELS.get(l, l) for l in (row["language_mix"] or [])],
        "outcome": oc_label,
        "outcome_status": oc_status,
        "sentiment": se_label,
        "sentiment_status": se_status,
        "sentiment_start": row["sentiment_start"],
        "sentiment_end": row["sentiment_end"],
        "csat": row["csat_predicted"] if row["handled_by"] != "abandoned" else None,
        "churn_risk": row["churn_risk"],
        "summary": row["summary"] or "No summary available for this call.",
        "key_points": derive_key_points(row),
    }
