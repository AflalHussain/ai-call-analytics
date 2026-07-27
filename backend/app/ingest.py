"""Call ingest — the single entry point for enriched call records.

Idempotent on call_id so the voice agent can retry safely.
"""

from __future__ import annotations

from typing import Any

from . import db, events
from .models import CallRecord, INTENT_LABELS

_UPSERT = """
INSERT INTO calls (
    call_id, started_at, ended_at, duration_sec, ai_handling_sec, queue_wait_sec,
    caller_hash, district, customer_segment, channel,
    intent, sub_intent, topics, language_primary, language_mix,
    handled_by, resolved, escalation_reason, actions_taken,
    sentiment_start, sentiment_end, csat_predicted, interruptions, silence_ratio,
    churn_risk, churn_signals, upsell_opportunity, unanswered_questions,
    summary, enrichment_model, enrichment_confidence, schema_version,
    affected_number, callback_number, caller_number
) VALUES (
    $1,$2,$3,$4,$5,$6,
    $7,$8,$9,$10,
    $11,$12,$13,$14,$15,
    $16,$17,$18,$19,
    $20,$21,$22,$23,$24,
    $25,$26,$27,$28,
    $29,$30,$31,$32,
    $33,$34,$35
)
ON CONFLICT (call_id) DO UPDATE SET
    started_at = EXCLUDED.started_at,
    ended_at = EXCLUDED.ended_at,
    duration_sec = EXCLUDED.duration_sec,
    ai_handling_sec = EXCLUDED.ai_handling_sec,
    queue_wait_sec = EXCLUDED.queue_wait_sec,
    caller_hash = EXCLUDED.caller_hash,
    district = EXCLUDED.district,
    customer_segment = EXCLUDED.customer_segment,
    channel = EXCLUDED.channel,
    intent = EXCLUDED.intent,
    sub_intent = EXCLUDED.sub_intent,
    topics = EXCLUDED.topics,
    language_primary = EXCLUDED.language_primary,
    language_mix = EXCLUDED.language_mix,
    handled_by = EXCLUDED.handled_by,
    resolved = EXCLUDED.resolved,
    escalation_reason = EXCLUDED.escalation_reason,
    actions_taken = EXCLUDED.actions_taken,
    sentiment_start = EXCLUDED.sentiment_start,
    sentiment_end = EXCLUDED.sentiment_end,
    csat_predicted = EXCLUDED.csat_predicted,
    interruptions = EXCLUDED.interruptions,
    silence_ratio = EXCLUDED.silence_ratio,
    churn_risk = EXCLUDED.churn_risk,
    churn_signals = EXCLUDED.churn_signals,
    upsell_opportunity = EXCLUDED.upsell_opportunity,
    unanswered_questions = EXCLUDED.unanswered_questions,
    summary = EXCLUDED.summary,
    enrichment_model = EXCLUDED.enrichment_model,
    enrichment_confidence = EXCLUDED.enrichment_confidence,
    schema_version = EXCLUDED.schema_version,
    affected_number = EXCLUDED.affected_number,
    callback_number = EXCLUDED.callback_number,
    caller_number = EXCLUDED.caller_number,
    ingested_at = now();
"""


def _row(c: CallRecord) -> tuple:
    def val(x):
        return x.value if hasattr(x, "value") else x

    return (
        c.call_id, c.started_at, c.ended_at, c.duration_sec,
        c.ai_handling_sec, c.queue_wait_sec,
        c.caller_hash, c.district, val(c.customer_segment), c.channel,
        val(c.intent), c.sub_intent, c.topics, val(c.language_primary),
        [val(x) for x in c.language_mix],
        val(c.handled_by), c.resolved, val(c.escalation_reason),
        [a.model_dump() for a in c.actions_taken],
        c.sentiment_start, c.sentiment_end, c.csat_predicted,
        c.interruptions, c.silence_ratio,
        c.churn_risk, c.churn_signals, c.upsell_opportunity,
        c.unanswered_questions,
        c.summary, c.enrichment_model, c.enrichment_confidence, c.schema_version,
        c.affected_number, c.callback_number, c.caller_number,
    )


async def store(calls: list[CallRecord], broadcast: bool = True) -> int:
    """Upsert calls. Returns the number written."""
    if not calls:
        return 0

    # actions_taken (param 19, a list[dict]) is encoded by the connection-level
    # jsonb codec — which applies to executemany too. Pre-stringifying it here
    # would double-encode (codec dumps the already-dumped string), storing a
    # jsonb *string* instead of a jsonb array. Pass the list through as-is.
    rows = [_row(c) for c in calls]

    async with db.pool().acquire() as conn:
        await conn.executemany(_UPSERT, rows)

    if broadcast:
        for c in calls:
            events.publish("call", _live_payload(c))

    return len(calls)


def _live_payload(c: CallRecord) -> dict[str, Any]:
    """Compact shape for the live feed ticker."""
    intent = c.intent.value if hasattr(c.intent, "value") else c.intent
    return {
        "call_id": c.call_id,
        "started_at": c.started_at.isoformat(),
        "intent": intent,
        "label": INTENT_LABELS.get(intent, intent),
        "district": c.district,
        "language": c.language_primary.value if hasattr(c.language_primary, "value") else c.language_primary,
        "handled_by": c.handled_by.value if hasattr(c.handled_by, "value") else c.handled_by,
        "resolved": c.resolved,
        "duration_sec": c.duration_sec,
        "sentiment_start": c.sentiment_start,
        "sentiment_end": c.sentiment_end,
        "churn_risk": c.churn_risk,
        "summary": c.summary,
    }
