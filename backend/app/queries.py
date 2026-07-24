"""All analytics SQL lives here — one function per endpoint.

Everything is a plain aggregate over `calls`. No precomputation, no materialised
views: at demo scale (~10k rows) each of these is single-digit milliseconds.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from . import db
from .models import (
    ESCALATION_LABELS,
    INTENT_LABELS,
    LANGUAGE_LABELS,
)

# Calls outside business hours OR at a weekend — i.e. calls their current
# contact centre would simply have lost.
_AFTER_HOURS = """
    (
        (c.started_at AT TIME ZONE cfg.timezone)::time < cfg.business_hours_start
     OR (c.started_at AT TIME ZONE cfg.timezone)::time >= cfg.business_hours_end
     OR EXTRACT(dow FROM c.started_at AT TIME ZONE cfg.timezone) IN (0, 6)
    )
"""


async def kpis(frm: datetime, to: datetime) -> dict[str, Any]:
    """Layer 1 — the executive / ROI strip."""
    sql = f"""
    WITH cfg AS (SELECT * FROM config WHERE id = 1),
    agg AS (
        SELECT
            count(*)                                                   AS total_calls,
            count(*) FILTER (WHERE c.handled_by = 'ai')                AS ai_handled,
            count(*) FILTER (WHERE c.handled_by = 'escalated')         AS escalated,
            count(*) FILTER (WHERE c.handled_by = 'abandoned')         AS abandoned,
            count(*) FILTER (WHERE c.handled_by = 'transferred_ivr')   AS transferred_ivr,
            count(*) FILTER (WHERE {_AFTER_HOURS})                     AS after_hours_calls,
            count(*) FILTER (WHERE {_AFTER_HOURS} AND c.handled_by = 'ai')
                                                                       AS after_hours_handled,
            avg(c.duration_sec) FILTER (WHERE c.handled_by = 'ai')     AS avg_ai_duration_sec,
            avg(c.csat_predicted)                                      AS avg_csat,
            avg(c.sentiment_end)                                       AS avg_sentiment_end,
            avg(c.sentiment_end - c.sentiment_start)                   AS avg_sentiment_delta,
            count(*) FILTER (WHERE c.resolved)                         AS resolved_calls,
            count(*) FILTER (WHERE c.churn_risk)                       AS churn_flagged
        FROM calls c CROSS JOIN cfg
        WHERE c.started_at >= $1 AND c.started_at < $2
    )
    SELECT agg.*, cfg.* FROM agg CROSS JOIN cfg;
    """
    async with db.pool().acquire() as conn:
        row = await conn.fetchrow(sql, frm, to)
        repeat_pct = await _repeat_caller_pct(conn, frm, to)

    total = row["total_calls"] or 0
    ai = row["ai_handled"] or 0

    containment_pct = (ai / total * 100) if total else 0.0
    abandon_pct = ((row["abandoned"] or 0) / total * 100) if total else 0.0

    return {
        "range": {"from": frm.isoformat(), "to": to.isoformat()},
        "total_calls": total,
        "ai_handled": ai,
        "escalated": row["escalated"] or 0,
        "abandoned": row["abandoned"] or 0,
        "transferred_ivr": row["transferred_ivr"] or 0,
        "containment_pct": round(containment_pct, 1),
        "resolution_pct": round((row["resolved_calls"] or 0) / total * 100, 1) if total else 0.0,
        "avg_ai_duration_sec": round(row["avg_ai_duration_sec"] or 0),
        "after_hours_calls": row["after_hours_calls"] or 0,
        "after_hours_pct": round((row["after_hours_calls"] or 0) / total * 100, 1) if total else 0.0,
        "after_hours_handled": row["after_hours_handled"] or 0,
        "avg_csat": round(row["avg_csat"] or 0, 2),
        "avg_sentiment_end": round(row["avg_sentiment_end"] or 0, 2),
        "avg_sentiment_delta": round(row["avg_sentiment_delta"] or 0, 2),
        "abandon_pct": round(abandon_pct, 1),
        "repeat_caller_pct": round(repeat_pct, 1),
        "churn_flagged": row["churn_flagged"] or 0,
    }


async def _repeat_caller_pct(conn, frm: datetime, to: datetime) -> float:
    """Share of calls where the same caller had already called in the prior 24h.

    A first-contact-resolution proxy: high repeat rate means calls are being
    "handled" without actually being solved.
    """
    sql = """
    WITH scoped AS (
        SELECT call_id, caller_hash, started_at
        FROM calls
        WHERE started_at >= $1 AND started_at < $2 AND caller_hash IS NOT NULL
    )
    SELECT
        count(*) FILTER (WHERE EXISTS (
            SELECT 1 FROM calls p
            WHERE p.caller_hash = s.caller_hash
              AND p.call_id <> s.call_id
              AND p.started_at <  s.started_at
              AND p.started_at >= s.started_at - interval '24 hours'
        ))::float AS repeats,
        count(*)::float AS total
    FROM scoped s;
    """
    row = await conn.fetchrow(sql, frm, to)
    return (row["repeats"] / row["total"] * 100) if row["total"] else 0.0


async def timeline(frm: datetime, to: datetime) -> list[dict[str, Any]]:
    """Daily series powering the exec-strip sparklines."""
    sql = """
    WITH cfg AS (SELECT * FROM config WHERE id = 1)
    SELECT
        (c.started_at AT TIME ZONE cfg.timezone)::date         AS day,
        count(*)::int                                          AS calls,
        count(*) FILTER (WHERE c.handled_by = 'ai')::int       AS contained,
        avg(c.csat_predicted)::real                            AS avg_csat,
        avg(c.sentiment_end - c.sentiment_start)::real         AS sentiment_delta
    FROM calls c CROSS JOIN cfg
    WHERE c.started_at >= $1 AND c.started_at < $2
    GROUP BY 1 ORDER BY 1;
    """
    async with db.pool().acquire() as conn:
        rows = await conn.fetch(sql, frm, to)
    return [
        {
            "day": r["day"].isoformat(),
            "calls": r["calls"],
            "contained": r["contained"],
            "containment_pct": round(r["contained"] / r["calls"] * 100, 1) if r["calls"] else 0,
            "avg_csat": round(r["avg_csat"] or 0, 2),
            "sentiment_delta": round(r["sentiment_delta"] or 0, 2),
        }
        for r in rows
    ]


async def volume_heatmap(frm: datetime, to: datetime) -> list[dict[str, Any]]:
    """Hour x day-of-week volume — the staffing chart."""
    sql = """
    WITH cfg AS (SELECT * FROM config WHERE id = 1)
    SELECT
        EXTRACT(dow  FROM c.started_at AT TIME ZONE cfg.timezone)::int AS dow,
        EXTRACT(hour FROM c.started_at AT TIME ZONE cfg.timezone)::int AS hour,
        count(*)::int                                                  AS calls,
        count(*) FILTER (WHERE c.handled_by = 'ai')::int               AS contained
    FROM calls c CROSS JOIN cfg
    WHERE c.started_at >= $1 AND c.started_at < $2
    GROUP BY 1, 2;
    """
    async with db.pool().acquire() as conn:
        rows = await conn.fetch(sql, frm, to)
    return [dict(r) for r in rows]


async def intents(frm: datetime, to: datetime) -> list[dict[str, Any]]:
    """Intent distribution + containment by intent.

    The containment column is the deliberately honest one: it shows exactly
    where the agent wins and where it hands off.
    """
    sql = """
    SELECT
        intent,
        count(*)::int                                       AS total,
        count(*) FILTER (WHERE handled_by = 'ai')::int      AS contained,
        count(*) FILTER (WHERE handled_by = 'escalated')::int AS escalated,
        avg(duration_sec)::real                             AS avg_duration_sec,
        avg(sentiment_end - sentiment_start)::real          AS sentiment_delta,
        avg(csat_predicted)::real                           AS avg_csat
    FROM calls
    WHERE started_at >= $1 AND started_at < $2
    GROUP BY intent
    ORDER BY total DESC;
    """
    async with db.pool().acquire() as conn:
        rows = await conn.fetch(sql, frm, to)
    return [
        {
            "intent": r["intent"],
            "label": INTENT_LABELS.get(r["intent"], r["intent"]),
            "total": r["total"],
            "contained": r["contained"],
            "escalated": r["escalated"],
            "containment_pct": round(r["contained"] / r["total"] * 100, 1) if r["total"] else 0,
            "avg_duration_sec": round(r["avg_duration_sec"] or 0),
            "sentiment_delta": round(r["sentiment_delta"] or 0, 2),
            "avg_csat": round(r["avg_csat"] or 0, 2),
        }
        for r in rows
    ]


async def escalations(frm: datetime, to: datetime) -> list[dict[str, Any]]:
    """Why the agent handed off. This chart is the product roadmap."""
    sql = """
    SELECT escalation_reason AS reason, count(*)::int AS total
    FROM calls
    WHERE started_at >= $1 AND started_at < $2
      AND handled_by = 'escalated' AND escalation_reason IS NOT NULL
    GROUP BY 1 ORDER BY total DESC;
    """
    async with db.pool().acquire() as conn:
        rows = await conn.fetch(sql, frm, to)
    total = sum(r["total"] for r in rows) or 1
    return [
        {
            "reason": r["reason"],
            "label": ESCALATION_LABELS.get(r["reason"], r["reason"]),
            "total": r["total"],
            "share_pct": round(r["total"] / total * 100, 1),
        }
        for r in rows
    ]


async def languages(frm: datetime, to: datetime) -> dict[str, Any]:
    """Sinhala / Tamil / English mix, plus containment and CSAT per language.

    Equal performance across all three is the hard differentiator against
    vendors who only really work in English.
    """
    by_lang_sql = """
    SELECT
        language_primary                                    AS lang,
        count(*)::int                                       AS total,
        count(*) FILTER (WHERE handled_by = 'ai')::int      AS contained,
        avg(csat_predicted)::real                           AS avg_csat,
        count(*) FILTER (WHERE cardinality(language_mix) > 1)::int AS code_switched
    FROM calls
    WHERE started_at >= $1 AND started_at < $2
    GROUP BY 1 ORDER BY total DESC;
    """
    by_district_sql = """
    SELECT district, language_primary AS lang, count(*)::int AS total
    FROM calls
    WHERE started_at >= $1 AND started_at < $2 AND district IS NOT NULL
    GROUP BY 1, 2;
    """
    async with db.pool().acquire() as conn:
        lang_rows = await conn.fetch(by_lang_sql, frm, to)
        dist_rows = await conn.fetch(by_district_sql, frm, to)

    by_language = [
        {
            "lang": r["lang"],
            "label": LANGUAGE_LABELS.get(r["lang"], r["lang"]),
            "total": r["total"],
            "contained": r["contained"],
            "containment_pct": round(r["contained"] / r["total"] * 100, 1) if r["total"] else 0,
            "avg_csat": round(r["avg_csat"] or 0, 2),
            "code_switched": r["code_switched"],
        }
        for r in lang_rows
    ]

    districts: dict[str, dict[str, Any]] = {}
    for r in dist_rows:
        d = districts.setdefault(r["district"], {"district": r["district"], "si": 0, "ta": 0, "en": 0})
        d[r["lang"]] = r["total"]
    by_district = sorted(
        districts.values(), key=lambda d: d["si"] + d["ta"] + d["en"], reverse=True
    )[:10]

    return {"by_language": by_language, "by_district": by_district}


async def sentiment(frm: datetime, to: datetime) -> dict[str, Any]:
    """Start -> end sentiment. Proves the agent de-escalates rather than enrages."""
    overall_sql = """
    SELECT
        avg(sentiment_start)::real                  AS avg_start,
        avg(sentiment_end)::real                    AS avg_end,
        count(*) FILTER (WHERE sentiment_end > sentiment_start)::int AS improved,
        count(*) FILTER (WHERE sentiment_end < sentiment_start)::int AS worsened,
        count(*)::int                               AS total
    FROM calls
    WHERE started_at >= $1 AND started_at < $2
      AND sentiment_start IS NOT NULL AND sentiment_end IS NOT NULL;
    """
    by_intent_sql = """
    SELECT intent,
           avg(sentiment_start)::real AS avg_start,
           avg(sentiment_end)::real   AS avg_end,
           count(*)::int              AS total
    FROM calls
    WHERE started_at >= $1 AND started_at < $2
      AND sentiment_start IS NOT NULL AND sentiment_end IS NOT NULL
    GROUP BY intent
    HAVING count(*) > 20
    ORDER BY total DESC LIMIT 8;
    """
    async with db.pool().acquire() as conn:
        o = await conn.fetchrow(overall_sql, frm, to)
        rows = await conn.fetch(by_intent_sql, frm, to)

    total = o["total"] or 1
    return {
        "avg_start": round(o["avg_start"] or 0, 2),
        "avg_end": round(o["avg_end"] or 0, 2),
        "delta": round((o["avg_end"] or 0) - (o["avg_start"] or 0), 2),
        "improved_pct": round((o["improved"] or 0) / total * 100, 1),
        "worsened_pct": round((o["worsened"] or 0) / total * 100, 1),
        "by_intent": [
            {
                "intent": r["intent"],
                "label": INTENT_LABELS.get(r["intent"], r["intent"]),
                "avg_start": round(r["avg_start"], 2),
                "avg_end": round(r["avg_end"], 2),
                "delta": round(r["avg_end"] - r["avg_start"], 2),
                "total": r["total"],
            }
            for r in rows
        ],
    }


async def churn_feed(frm: datetime, to: datetime, limit: int = 40) -> dict[str, Any]:
    """Calls carrying churn signals — a retention callback queue."""
    feed_sql = """
    SELECT call_id, started_at, district, intent, customer_segment,
           churn_signals, sentiment_end, summary, handled_by
    FROM calls
    WHERE churn_risk AND started_at >= $1 AND started_at < $2
    ORDER BY started_at DESC
    LIMIT $3;
    """
    signals_sql = """
    SELECT s AS signal, count(*)::int AS total
    FROM calls, unnest(churn_signals) AS s
    WHERE churn_risk AND started_at >= $1 AND started_at < $2
    GROUP BY 1 ORDER BY total DESC LIMIT 8;
    """
    async with db.pool().acquire() as conn:
        rows = await conn.fetch(feed_sql, frm, to, limit)
        sig_rows = await conn.fetch(signals_sql, frm, to)
        total = await conn.fetchval(
            "SELECT count(*)::int FROM calls WHERE churn_risk "
            "AND started_at >= $1 AND started_at < $2",
            frm, to,
        )

    return {
        "total": total,
        "top_signals": [dict(r) for r in sig_rows],
        "calls": [
            {
                "call_id": r["call_id"],
                "started_at": r["started_at"].isoformat(),
                "district": r["district"],
                "intent": r["intent"],
                "label": INTENT_LABELS.get(r["intent"], r["intent"]),
                "customer_segment": r["customer_segment"],
                "churn_signals": list(r["churn_signals"]),
                "sentiment_end": round(r["sentiment_end"] or 0, 2),
                "summary": r["summary"],
                "handled_by": r["handled_by"],
            }
            for r in rows
        ],
    }


async def knowledge_gaps(frm: datetime, to: datetime, limit: int = 12) -> list[dict[str, Any]]:
    """Questions the agent could not answer, ranked. Their next-quarter backlog."""
    sql = """
    SELECT q AS question, count(*)::int AS total,
           mode() WITHIN GROUP (ORDER BY intent) AS common_intent
    FROM calls, unnest(unanswered_questions) AS q
    WHERE started_at >= $1 AND started_at < $2
    GROUP BY q
    ORDER BY total DESC
    LIMIT $3;
    """
    async with db.pool().acquire() as conn:
        rows = await conn.fetch(sql, frm, to, limit)
    return [
        {
            "question": r["question"],
            "total": r["total"],
            "intent": r["common_intent"],
            "label": INTENT_LABELS.get(r["common_intent"], r["common_intent"]),
        }
        for r in rows
    ]


async def upsell(frm: datetime, to: datetime) -> list[dict[str, Any]]:
    """Cross-sell / upsell signals — revenue upside, not just cost reduction."""
    sql = """
    SELECT upsell_opportunity AS opportunity,
           count(*)::int AS total,
           count(*) FILTER (WHERE handled_by = 'ai')::int AS contained
    FROM calls
    WHERE started_at >= $1 AND started_at < $2 AND upsell_opportunity IS NOT NULL
    GROUP BY 1 ORDER BY total DESC LIMIT 10;
    """
    async with db.pool().acquire() as conn:
        rows = await conn.fetch(sql, frm, to)
    return [dict(r) for r in rows]
