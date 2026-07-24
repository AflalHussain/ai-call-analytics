"""Emerging-issue detection.

The single most differentiating panel on the dashboard: a call agent surfacing
a network problem before the network team has raised a ticket.

Method: for each (intent, district) and each topic, compare the count in the
most recent 2-hour window against the same 2-hour-of-day window on each of the
previous 7 days. Fire when the z-score clears the threshold AND the absolute
count clears a floor — the floor is what stops low-volume districts generating
a "300% spike" from 1 call to 4.

The detection window is anchored to the newest call in the database, not to
wall-clock now. That keeps the panel alive on seeded data regardless of when
the dashboard is opened. See README "Demo-day runbook" — the seed should still
be regenerated on the morning of the demo so the timestamps read as today.
"""

from __future__ import annotations

import statistics
from datetime import datetime, timedelta
from typing import Any

from . import db
from .models import INTENT_LABELS

WINDOW = timedelta(hours=2)
BASELINE_DAYS = 7

# Tuning. Both conditions must hold.
Z_THRESHOLD = 3.0
MIN_COUNT = 5

# Guards against a zero-variance baseline producing an infinite z-score.
MIN_STD = 1.0


async def _anchor(conn) -> datetime | None:
    return await conn.fetchval("SELECT max(started_at) FROM calls")


async def _counts(conn, dimension: str, start: datetime, end: datetime) -> dict[tuple, int]:
    """Counts keyed by dimension over [start, end)."""
    if dimension == "intent_district":
        sql = """
        SELECT intent, coalesce(district, 'unknown') AS district, count(*)::int AS c
        FROM calls WHERE started_at >= $1 AND started_at < $2
        GROUP BY 1, 2;
        """
        rows = await conn.fetch(sql, start, end)
        return {(r["intent"], r["district"]): r["c"] for r in rows}

    sql = """
    SELECT t AS topic, count(*)::int AS c
    FROM calls, unnest(topics) AS t
    WHERE started_at >= $1 AND started_at < $2
    GROUP BY 1;
    """
    rows = await conn.fetch(sql, start, end)
    return {(r["topic"],): r["c"] for r in rows}


async def _members(conn, dimension: str, start: datetime, end: datetime) -> dict[tuple, set[str]]:
    """The actual call_ids behind each key — used to collapse duplicate alerts."""
    if dimension == "intent_district":
        sql = """
        SELECT intent, coalesce(district, 'unknown') AS district,
               array_agg(call_id) AS ids
        FROM calls WHERE started_at >= $1 AND started_at < $2
        GROUP BY 1, 2;
        """
        rows = await conn.fetch(sql, start, end)
        return {(r["intent"], r["district"]): set(r["ids"]) for r in rows}

    sql = """
    SELECT t AS topic, array_agg(call_id) AS ids
    FROM calls, unnest(topics) AS t
    WHERE started_at >= $1 AND started_at < $2
    GROUP BY 1;
    """
    rows = await conn.fetch(sql, start, end)
    return {(r["topic"],): set(r["ids"]) for r in rows}


def _headline(dimension: str, key: tuple, pct_change: float, count: int, mean: float) -> str:
    """Phrase the alert the way an ops manager would say it out loud.

    A percentage is only meaningful when the baseline is non-trivial. "Up 7743%"
    off a baseline of 0.3 calls is arithmetically true and rhetorically useless —
    it reads as a broken metric and invites exactly the wrong question. Below one
    call per window we state the raw numbers instead.
    """
    if dimension == "intent_district":
        intent, district = key
        subject = f"{INTENT_LABELS.get(intent, intent)} calls"
        where = "" if district == "unknown" else f" in {district}"
    else:
        subject = f'"{key[0]}" mentions'
        where = ""

    if mean < 1.0:
        return f"{subject}{where}: {count} in the last 2 hours — normally under 1"
    return (
        f"{subject} up {pct_change:+.0f}%{where} in the last 2 hours "
        f"({count} calls vs {mean:.0f} typical)"
    )


def _collapse(spikes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fold spikes that describe the same incident into one alert.

    A single broadband outage in Gampaha legitimately trips four detectors:
    (broadband_fault, Gampaha), and the topics "outage", "no_connection" and
    "fibre" — because they are largely the *same calls*. Presenting four alarms
    for one incident is the fastest way for an ops manager to conclude the
    detector is noise. So we keep the strongest signal and demote the rest to
    corroborating evidence, which is also more persuasive: one alert that says
    "and here are three independent signals agreeing" beats four alerts.

    Overlap is measured on actual call_id sets, so this is a real correlation
    rather than a hand-maintained list of related topics.
    """
    OVERLAP = 0.6
    # Prefer intent+district as the primary: it names a service and a place,
    # which is what someone can actually act on. Topics corroborate.
    spikes.sort(
        key=lambda s: (s["kind"] == "intent_district_spike", s["z_score"]),
        reverse=True,
    )

    kept: list[dict[str, Any]] = []
    for s in spikes:
        ids = s["_members"]
        primary = None
        for k in kept:
            if not ids:
                break
            overlap = len(ids & k["_members"]) / len(ids)
            if overlap >= OVERLAP:
                primary = k
                break
        if primary is None:
            s["corroborating"] = []
            kept.append(s)
        elif s["_label"] not in primary["corroborating"]:
            primary["corroborating"].append(s["_label"])

    for s in kept:
        s.pop("_members", None)
        s.pop("_label", None)
    return kept


async def detect(persist: bool = True) -> list[dict[str, Any]]:
    """Run detection. Returns the spikes found; optionally writes them to `alerts`."""
    async with db.pool().acquire() as conn:
        anchor = await _anchor(conn)
        if anchor is None:
            return []

        window_start = anchor - WINDOW
        found: list[dict[str, Any]] = []

        for dimension in ("intent_district", "topic"):
            current = await _counts(conn, dimension, window_start, anchor)
            if not current:
                continue
            members = await _members(conn, dimension, window_start, anchor)

            # Baseline: the same clock window on each of the previous 7 days.
            baselines: dict[tuple, list[int]] = {k: [] for k in current}
            for day in range(1, BASELINE_DAYS + 1):
                offset = timedelta(days=day)
                past = await _counts(
                    conn, dimension, window_start - offset, anchor - offset
                )
                # Zero-fill: a key absent from a past window genuinely had 0
                # calls then. Skipping it would inflate the mean and hide spikes.
                for key in baselines:
                    baselines[key].append(past.get(key, 0))

            for key, count in current.items():
                if count < MIN_COUNT:
                    continue
                sample = baselines[key]
                mean = statistics.fmean(sample)
                std = max(statistics.pstdev(sample), MIN_STD)
                z = (count - mean) / std
                if z < Z_THRESHOLD:
                    continue

                pct_change = (count - mean) / max(mean, 0.5) * 100
                # Severity needs absolute volume as well as a high z-score.
                # Sparse baselines make z alone unreliable — 1 call becoming 6
                # is statistically loud but operationally uninteresting.
                severity = "critical" if (z >= 5 and count >= 15) else "warning"
                spike = {
                    "kind": "intent_district_spike" if dimension == "intent_district" else "topic_spike",
                    "intent": key[0] if dimension == "intent_district" else None,
                    "district": key[1] if dimension == "intent_district" else None,
                    "topic": key[0] if dimension == "topic" else None,
                    "window_count": count,
                    "baseline_mean": round(mean, 2),
                    "baseline_std": round(std, 2),
                    "z_score": round(z, 2),
                    "pct_change": round(pct_change, 1),
                    "severity": severity,
                    "headline": _headline(dimension, key, pct_change, count, mean),
                    "dedupe_key": ":".join(["spike", dimension, *[str(k) for k in key]]),
                    "_members": members.get(key, set()),
                    "_label": key[0] if dimension == "topic" else INTENT_LABELS.get(key[0], key[0]),
                }
                found.append(spike)

        found = _collapse(found)

        if persist:
            # Auto-resolve anything that is no longer spiking. Without this an
            # alert lingers forever once fired, and the panel becomes a list of
            # things that were true at some point — which nobody trusts.
            live_keys = [s["dedupe_key"] for s in found]
            await conn.execute(
                """
                UPDATE alerts SET resolved_at = now()
                WHERE resolved_at IS NULL AND NOT (dedupe_key = ANY($1::text[]))
                """,
                live_keys,
            )

        if persist and found:
            await conn.executemany(
                """
                INSERT INTO alerts (kind, intent, district, topic, window_count,
                                    baseline_mean, baseline_std, z_score,
                                    pct_change, severity, headline, dedupe_key,
                                    corroborating)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
                ON CONFLICT (dedupe_key) WHERE resolved_at IS NULL
                DO UPDATE SET window_count  = EXCLUDED.window_count,
                              baseline_mean = EXCLUDED.baseline_mean,
                              z_score       = EXCLUDED.z_score,
                              pct_change    = EXCLUDED.pct_change,
                              severity      = EXCLUDED.severity,
                              headline      = EXCLUDED.headline,
                              corroborating = EXCLUDED.corroborating,
                              detected_at   = now();
                """,
                [
                    (
                        s["kind"], s["intent"], s["district"], s["topic"],
                        s["window_count"], s["baseline_mean"], s["baseline_std"],
                        s["z_score"], s["pct_change"], s["severity"],
                        s["headline"], s["dedupe_key"], s.get("corroborating", []),
                    )
                    for s in found
                ],
            )

    return found


async def active_alerts(limit: int = 10) -> list[dict[str, Any]]:
    """Alerts for the panel. Runs detection first so the page is never stale."""
    await detect(persist=True)
    sql = """
    SELECT id, detected_at, kind, intent, district, topic, window_count,
           baseline_mean, z_score, pct_change, severity, headline, corroborating
    FROM alerts
    WHERE resolved_at IS NULL
    ORDER BY (severity = 'critical') DESC, z_score DESC
    LIMIT $1;
    """
    async with db.pool().acquire() as conn:
        rows = await conn.fetch(sql, limit)
    return [
        {
            **dict(r),
            "detected_at": r["detected_at"].isoformat(),
            "corroborating": list(r["corroborating"]),
        }
        for r in rows
    ]
