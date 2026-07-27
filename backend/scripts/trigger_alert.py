#!/usr/bin/env python3
"""Fire a fresh emerging-issue alert for a chosen district — live, on stage.

The "Needs attention now" panel is driven by the spike detector in app/alerts.py:
for each (intent, district) it compares the last 2 hours against the same window
on the previous 7 days, and fires when

    z-score >= 3   AND   count >= 5           -> WARNING
    z-score >= 5   AND   count >= 15          -> CRITICAL

So to make a *new* card appear for a district that isn't already spiking, we POST
a burst of same-intent, same-district calls timestamped inside the last 2 hours.
They go through the real /ingest/call path, which runs detection and pushes the
new alert over SSE — so the card appears on the open dashboard within a second,
exactly as a real incident would.

Examples
--------
    # A critical broadband incident in Kandy (default)
    python scripts/trigger_alert.py --district Kandy

    # A warning-level PEO TV spike in Jaffna
    python scripts/trigger_alert.py --district Jaffna --intent peo_tv --severity warning

    # A mobile-coverage outage in Batticaloa, Tamil-language area
    python scripts/trigger_alert.py --district Batticaloa --intent mobile_coverage
"""

from __future__ import annotations

import argparse
import hashlib
import random
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models import DISTRICTS, INTENT_LABELS  # noqa: E402
from app.phone import affected_number  # noqa: E402

TZ = ZoneInfo("Asia/Colombo")

# Topics/summary per intent so the card's "corroborated by" line and the live
# feed rows read like a real incident rather than filler.
INTENT_PROFILE: dict[str, dict] = {
    "broadband_fault": {
        "topics": ["outage", "no_connection", "fibre"],
        "containment": 0.38,
        "sentiment": (-0.72, 0.15),
        "summary": "Customer in {d} reported broadband down. Multiple reports from the same area — suspected local outage. Fault ticket raised.",
    },
    "broadband_speed": {
        "topics": ["slow_speed", "throttling", "fibre"],
        "containment": 0.46,
        "sentiment": (-0.55, 0.10),
        "summary": "Customer in {d} reported speeds far below package across the area.",
    },
    "mobile_coverage": {
        "topics": ["signal", "dropped_calls", "tower"],
        "containment": 0.50,
        "sentiment": (-0.60, 0.12),
        "summary": "Customer in {d} reported no signal / dropped calls. Cell status checked, coverage ticket raised.",
    },
    "peo_tv": {
        "topics": ["peo_tv", "channels", "set_top_box"],
        "containment": 0.55,
        "sentiment": (-0.40, 0.20),
        "summary": "Customer in {d} reported PEO TV channels down. Suspected area-wide signal issue.",
    },
    "router_wifi": {
        "topics": ["router", "wifi", "equipment"],
        "containment": 0.58,
        "sentiment": (-0.35, 0.15),
        "summary": "Customer in {d} reported router / WiFi failure after a suspected area power event.",
    },
}

# District → language weights, so a Jaffna or Batticaloa burst reads as Tamil.
LANG_BY_DISTRICT: dict[str, tuple[float, float, float]] = {
    "Jaffna": (0.06, 0.89, 0.05), "Kilinochchi": (0.04, 0.93, 0.03),
    "Mannar": (0.10, 0.86, 0.04), "Vavuniya": (0.20, 0.76, 0.04),
    "Mullaitivu": (0.05, 0.92, 0.03), "Batticaloa": (0.08, 0.87, 0.05),
    "Trincomalee": (0.35, 0.60, 0.05), "Ampara": (0.42, 0.54, 0.04),
    "Colombo": (0.62, 0.16, 0.22),
}
DEFAULT_LANG = (0.88, 0.07, 0.05)

# Severity → how many calls to send. Comfortably clears the count floors above,
# with headroom so a slightly noisy baseline still trips it.
SEVERITY_COUNT = {"warning": 8, "critical": 22}


def _pick_lang(district: str, rng: random.Random) -> tuple[str, list[str]]:
    p_si, p_ta, p_en = LANG_BY_DISTRICT.get(district, DEFAULT_LANG)
    primary = rng.choices(["si", "ta", "en"], weights=[p_si, p_ta, p_en], k=1)[0]
    mix = [primary]
    if primary != "en" and rng.random() < 0.34:
        mix.append("en")
    return primary, mix


def _clamp(v: float) -> float:
    return max(-1.0, min(1.0, v))


def build_burst(district: str, intent: str, count: int, rng: random.Random) -> list[dict]:
    prof = INTENT_PROFILE[intent]
    now = datetime.now(TZ).replace(microsecond=0)
    calls: list[dict] = []

    for _ in range(count):
        # Spread across the last ~110 min so the burst sits inside the 2-hour
        # detection window and looks organic on the timeline.
        started = now - timedelta(minutes=rng.uniform(2, 110), seconds=rng.randint(0, 59))
        duration = max(40, int(rng.gauss(240, 70)))
        contained = rng.random() < prof["containment"]
        s_start = _clamp(rng.gauss(*prof["sentiment"]) if False else rng.gauss(prof["sentiment"][0], prof["sentiment"][1]))
        s_end = _clamp(s_start + rng.uniform(0.1, 0.6))
        lang, lang_mix = _pick_lang(district, rng)
        msisdn = f"94{random.randint(700000000, 799999999)}"

        calls.append({
            "call_id": f"call_alert_{uuid.uuid4().hex[:16]}",
            "started_at": started.isoformat(),
            "ended_at": (started + timedelta(seconds=duration)).isoformat(),
            "duration_sec": duration,
            "ai_handling_sec": duration if contained else int(duration * 0.55),
            "queue_wait_sec": rng.randint(0, 4),
            "caller_hash": "sha256:" + hashlib.sha256(msisdn.encode()).hexdigest()[:32],
            "district": district,
            "customer_segment": rng.choice(["prepaid", "postpaid", "fixed"]),
            "channel": "voice_inbound",
            "affected_number": affected_number(intent, district, rng),
            "intent": intent,
            "topics": list(prof["topics"]),
            "language_primary": lang,
            "language_mix": lang_mix,
            "handled_by": "ai" if contained else "escalated",
            "resolved": contained,
            "escalation_reason": None if contained else "intent_not_supported",
            "actions_taken": [
                {"action": "lookup_account", "status": "ok"},
                {"action": "run_line_test", "status": "ok"},
                {"action": "raise_fault_ticket", "status": "ok", "ref": f"FLT-{rng.randint(100000, 999999)}"},
            ],
            "sentiment_start": round(s_start, 3),
            "sentiment_end": round(s_end, 3),
            "csat_predicted": rng.randint(2, 4),
            "interruptions": rng.randint(0, 2),
            "silence_ratio": round(abs(rng.gauss(0.09, 0.05)), 3),
            "churn_risk": False,
            "churn_signals": [],
            "upsell_opportunity": None,
            "unanswered_questions": [],
            "summary": prof["summary"].format(d=district),
            "enrichment_model": "claude-opus-4-8",
            "enrichment_confidence": round(rng.uniform(0.82, 0.98), 3),
            "schema_version": "0.1",
        })

    return calls


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--district", default="Kandy",
                    help="District for the new alert (default: Kandy). Must be a valid SL district.")
    ap.add_argument("--intent", default="broadband_fault", choices=sorted(INTENT_PROFILE),
                    help="Incident type (default: broadband_fault)")
    ap.add_argument("--severity", choices=["warning", "critical"], default="critical",
                    help="Target severity — sets how many calls to send (default: critical)")
    ap.add_argument("--count", type=int, default=None,
                    help="Override the number of calls (otherwise derived from --severity)")
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--seed", type=int, default=None, help="RNG seed for reproducibility")
    args = ap.parse_args()

    if args.district not in DISTRICTS:
        valid = ", ".join(d for d in DISTRICTS if d != "unknown")
        ap.error(f"unknown district {args.district!r}. Valid: {valid}")

    rng = random.Random(args.seed)
    count = args.count or SEVERITY_COUNT[args.severity]
    calls = build_burst(args.district, args.intent, count, rng)

    label = INTENT_LABELS.get(args.intent, args.intent)
    print(f"posting {count} {label} calls in {args.district} ...")

    r = httpx.post(f"{args.api}/ingest/call", json={"calls": calls}, timeout=30)
    r.raise_for_status()
    print(f"  -> {r.status_code} {r.json()}")

    # Read back the alert this produced so the operator sees it worked.
    alerts = httpx.get(f"{args.api}/api/alerts", timeout=15).json()
    mine = [a for a in alerts if a.get("district") == args.district and a.get("intent") == args.intent]
    if mine:
        a = mine[0]
        print(f"\n✓ alert live [{a['severity'].upper()}]: {a['headline']}")
        if a.get("corroborating"):
            print(f"  corroborated by: {', '.join(a['corroborating'])}")
    else:
        print("\n… no alert yet — the burst may be below the spike threshold for this "
              "district's baseline. Re-run with --severity critical, raise --count, or "
              "regenerate the seed so 'now' aligns with the newest call "
              "(see README demo-day runbook).")


if __name__ == "__main__":
    main()
