# Call Agent Dashboard — Enriched Call Record Contract

**Version:** 0.1 (draft)
**Status:** Awaiting sign-off — pipeline team implements, dashboard consumes.

One JSON object per completed call. Emitted after post-call enrichment finishes.

---

## 1. The record

```jsonc
{
  // ---- identity & timing -------------------------------------------------
  "call_id": "call_01HXYZ...",            // unique, stable
  "started_at": "2026-07-21T14:32:07+05:30",  // ISO 8601 WITH offset (+05:30)
  "ended_at":   "2026-07-21T14:35:41+05:30",
  "duration_sec": 214,                     // total call, wall clock
  "ai_handling_sec": 188,                  // time AI was in control
  "queue_wait_sec": 3,                     // before AI answered

  // ---- caller ------------------------------------------------------------
  "caller_hash": "sha256:9f2b...",         // hashed MSISDN — NEVER raw number
  "district": "Gampaha",                   // see §3
  "customer_segment": "prepaid",           // prepaid | postpaid | fixed | enterprise | unknown
  "channel": "voice_inbound",              // voice_inbound | voice_outbound | ivr_deflect

  // ---- what the call was about -------------------------------------------
  "intent": "broadband_fault",             // REQUIRED, from taxonomy §2
  "sub_intent": "no_connection",           // optional, free-form
  "topics": ["outage", "router", "gampaha"], // 0-6 tags, drives spike detection
  "language_primary": "si",                // si | ta | en
  "language_mix": ["si", "en"],            // all languages detected in the call

  // ---- outcome -----------------------------------------------------------
  "handled_by": "ai",                      // ai | escalated | abandoned | transferred_ivr
  "resolved": true,                        // did the caller's issue get closed
  "escalation_reason": null,               // see §4, null when handled_by == "ai"
  "actions_taken": [                       // what the agent actually DID
    { "action": "lookup_account",  "status": "ok" },
    { "action": "raise_fault_ticket", "status": "ok", "ref": "FLT-887213" }
  ],

  // ---- experience --------------------------------------------------------
  "sentiment_start": -0.62,                // -1.0 (angry) .. +1.0 (happy)
  "sentiment_end":    0.31,
  "csat_predicted":   4,                   // 1-5, model-estimated
  "interruptions": 1,                      // caller talked over agent
  "silence_ratio": 0.08,                   // 0-1, dead air fraction

  // ---- commercial & risk signals -----------------------------------------
  "churn_risk": true,
  "churn_signals": ["mentioned_competitor", "asked_about_disconnection"],
  "upsell_opportunity": "fibre_upgrade",   // null when none
  "unanswered_questions": [                // → knowledge-gap report
    "Can I pause my broadband while abroad?"
  ],

  // ---- provenance --------------------------------------------------------
  "summary": "Customer reported no broadband since morning in Ja-Ela...",
  "enrichment_model": "claude-opus-4-8",
  "enrichment_confidence": 0.91,           // 0-1; low values get flagged, not hidden
  "schema_version": "0.1"
}
```

### Field requirements

| Tier | Fields | Note |
|---|---|---|
| **Required** | `call_id`, `started_at`, `duration_sec`, `intent`, `language_primary`, `handled_by`, `resolved` | Dashboard breaks without these |
| **Strongly wanted** | `sentiment_start`, `sentiment_end`, `escalation_reason`, `district`, `ai_handling_sec`, `topics` | Layers 2–3 degrade without these |
| **Nice to have** | `churn_*`, `upsell_opportunity`, `unanswered_questions`, `actions_taken`, `csat_predicted` | Layer 3 differentiators; render as "—" if absent |

Unknown values: send `null`, never omit the key, never invent a value. `intent` falls back to `"other"` — never to a guess.

---

## 2. Intent taxonomy (fixed enum)

A closed set. New intents require a contract version bump — free-text intents make
the distribution chart useless.

| Value | Covers |
|---|---|
| `bill_inquiry` | Balance, charges, disputed amounts |
| `bill_payment` | Paying, payment failures, payment confirmation |
| `reload_topup` | Prepaid reload, reload failures |
| `data_package` | Activating / changing / checking data packages |
| `data_balance` | "How much data do I have left" |
| `broadband_fault` | Fixed broadband down / intermittent |
| `broadband_speed` | Slow speed complaints |
| `router_wifi` | Router, WiFi config, equipment |
| `mobile_coverage` | Signal, dropped calls, no service |
| `sim_services` | SIM replacement, activation, PUK, eSIM |
| `roaming` | International roaming activation, charges |
| `peo_tv` | PEO TV faults, packages, channels |
| `new_connection` | New mobile / broadband / PEO TV connection |
| `package_change` | Upgrade / downgrade / plan switch |
| `disconnection` | Cancellation, termination requests |
| `complaint_followup` | Chasing an existing ticket |
| `general_info` | Outlet locations, hours, general questions |
| `other` | Genuinely doesn't fit — keep this rare |

---

## 3. District (fixed enum)

Sri Lanka's 25 districts, plus `unknown`. Exact spellings:

`Colombo`, `Gampaha`, `Kalutara`, `Kandy`, `Matale`, `Nuwara Eliya`, `Galle`,
`Matara`, `Hambantota`, `Jaffna`, `Kilinochchi`, `Mannar`, `Vavuniya`,
`Mullaitivu`, `Batticaloa`, `Ampara`, `Trincomalee`, `Kurunegala`, `Puttalam`,
`Anuradhapura`, `Polonnaruwa`, `Badulla`, `Monaragala`, `Ratnapura`, `Kegalle`,
`unknown`

Used for the geographic spike alert ("broadband faults up 340% in Gampaha").

---

## 4. Escalation reason (fixed enum)

| Value | Meaning |
|---|---|
| `caller_requested_human` | Explicit ask |
| `intent_not_supported` | Outside the agent's scope |
| `authentication_failed` | Couldn't verify the customer |
| `repeated_misunderstanding` | ASR / comprehension breakdown |
| `high_frustration` | Sentiment-triggered handoff |
| `system_error` | Backend / API failure |
| `policy_required_human` | Business rule mandates a human |

This chart is the honest one. It is also the product roadmap — the top bar is
the next thing we build.

---

## 5. Transport

Two ways in, both accepted:

**A. Push (preferred for the live demo)**
```
POST /ingest/call        Content-Type: application/json
Body: the record above (single object) or {"calls": [...]} for batches
Auth: Authorization: Bearer <token>
Response: 202 Accepted
```
Idempotent on `call_id` — re-posting the same `call_id` upserts, so retries are safe.

**B. Bulk file (for backfill / seed)**
NDJSON, one record per line, gzip optional.

---

## 6. What the dashboard derives (do NOT send these)

These are computed from the records above. Sending them creates two sources of
truth that will disagree on stage.

- Containment rate — `handled_by == "ai"` / total
- Containment by intent
- After-hours coverage — from `started_at` vs. configured business hours
- Repeat-caller rate — `caller_hash` seen again within 24h
- Sentiment delta — `sentiment_end - sentiment_start`
- Emerging-issue alerts — `intent`/`topics`/`district` counts vs. 7-day baseline

---

## 7. Dashboard-side config (not per call)

Operational settings, set once:

```jsonc
{
  "business_hours": { "start": "08:30", "end": "17:30", "tz": "Asia/Colombo" }
}
```

Business hours drive the "answered outside office hours" KPI; the timezone
anchors the daily and heatmap aggregates to Sri Lanka local time. Confirm the
real business hours with SLT Mobitel so the after-hours figure is accurate.
