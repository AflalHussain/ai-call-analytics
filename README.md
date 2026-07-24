# Call Intelligence — analytics dashboard

Analytics and intelligence layer for the AI customer call handling agent, built
for the SLT Mobitel demo.

The prototype proves the agent can hold a call. This proves the agent is worth
buying — it answers the four questions the room will actually ask:

1. Is this saving me money? *(exec strip)*
2. Are my customers happier? *(sentiment, CSAT)*
3. What is the AI actually doing on my behalf? *(operations, escalation reasons)*
4. **What should I do tomorrow that I didn't know today?** *(emerging issues,
   churn risk, knowledge gaps)* ← the differentiator

---

## Quick start

Three terminals. Postgres runs on **5433** so it can't collide with a local one.

```bash
# 1. Database
docker compose up -d

# 2. Backend  (http://localhost:8000)
cd backend
python3 -m venv .venv && .venv/bin/pip install -e .
.venv/bin/python scripts/generate_seed.py --reset      # ~10k calls, ~20s
.venv/bin/uvicorn app.main:app --port 8000

# 3. Frontend (http://localhost:5173)
cd frontend
nvm use && npm install && npm run dev
```

Open **http://localhost:5173**. The API is proxied through Vite, so the demo
runs on a single port and there is no CORS to negotiate on a venue network.

---

## Demo-day runbook

**The morning of the demo, in this order:**

1. **Re-run the seed.** Everything is anchored to `now` at generation time, so
   fresh data means timestamps read as today and the emerging-issue alert sits
   inside its 2-hour detection window.
   ```bash
   cd backend && .venv/bin/python scripts/generate_seed.py --reset
   ```
2. **Start backend, then frontend.** Confirm `curl localhost:8000/health` shows
   a call count and a recent `newest_call`.
3. **Check the alert panel is populated** — the Gampaha broadband spike should
   be the top card. If it is missing, the seed is stale; re-run step 1.
4. **Set the theme.** Click ☀/☾ in the top bar to pick dark (projector) or light
   (bright room). The choice persists, so do it once and forget it.
5. **Dry-run the live call** (below) once, then `--reset` the seed again so the
   test call isn't sitting in the feed when you present.

**Presenting — the page is laid out in pitch order, top to bottom:**

| # | Section | Who it's for | The line |
|---|---|---|---|
| 1 | Needs attention now | Ops + CX | "Your call agent spotted a network incident in Gampaha before a ticket was raised." |
| 2 | Business impact | CFO | Flip **Compare to current contact centre** on stage — every figure becomes a delta against their own numbers. |
| 3 | Operations | Ops | Lead with containment-by-intent. It is deliberately unflattering; volunteering the weakness is what buys credibility. |
| 4 | Customer intelligence | CX + exec | Churn queue and knowledge gaps — this is the reframe from cost-centre automation to revenue and retention. |
| 5 | Live call | Everyone | Close here. Someone calls the number; the call lands in the feed within a second and the KPIs move. |

**Live call — two ways, same code path:**

```bash
# Real: the voice agent POSTs a DATA_CONTRACT.md record to /ingest/call

# Safety net, if that wiring isn't ready:
cd backend
.venv/bin/python scripts/seed_live_call.py --scenario tamil    # Tamil, resolved, happy
.venv/bin/python scripts/seed_live_call.py --scenario happy    # upsell signal detected
.venv/bin/python scripts/seed_live_call.py --scenario angry    # escalation + churn risk
.venv/bin/python scripts/seed_live_call.py --scenario outage   # feeds the Gampaha alert
```

Both routes go through the same `POST /ingest/call` handler, so if the pipeline
lands before demo day nothing needs to change.

**Live emerging-issue alert — make a new district light up on demand:**

`seed_live_call.py` adds one call; `trigger_alert.py` fires a whole *incident* —
a burst of same-intent, same-district calls in the last 2 hours — so a new card
appears in "Needs attention now" while the room watches. Same `/ingest/call`
path, so it pushes over SSE and lands within a second.

```bash
cd backend
# CRITICAL card for a new district (default: broadband_fault in Kandy)
.venv/bin/python scripts/trigger_alert.py --district Kandy

# choose district, incident type, and severity
.venv/bin/python scripts/trigger_alert.py --district Jaffna --intent peo_tv --severity warning
.venv/bin/python scripts/trigger_alert.py --district Batticaloa --intent mobile_coverage
```

Options: `--district` (any of the 25 SL districts), `--intent`
(`broadband_fault`, `broadband_speed`, `mobile_coverage`, `peo_tv`,
`router_wifi`), `--severity` (`warning` ≈ 8 calls / `critical` ≈ 22),
`--count` to override, `--seed` for reproducibility. Tamil-area districts get
Tamil-weighted calls automatically, so the live feed reads right too. The script
reads the alert back and prints it to confirm it fired.

Two rules for a clean panel on stage:

1. **Reset the seed first, then fire once.** The panel shows the top 3, sorted
   by severity then z-score. On a fresh seed there are two cards (Gampaha
   critical, Colombo warning), so one new critical lands in the visible three.
   Firing repeatedly without a reset piles up bursts and can push the newest
   card below the fold.
2. **Use a different `--intent` than an already-active incident.** The seed
   ships a `broadband_fault` incident in Gampaha. Triggering `broadband_fault`
   elsewhere makes both share the topics `outage`/`no_connection`/`fibre`; that
   shared topic spans two districts, doesn't fold into either, and surfaces as a
   noisy district-less "no_connection mentions up" card. `mobile_coverage` is
   the cleanest second incident — no topic overlap.

---

## ⚠️ Before you quote a savings number

The exec strip currently runs on **placeholder cost inputs** and says so on
screen. With a CFO in the room, an assumed cost rate will be challenged and the
number will be lost. Get these three figures from SLT Mobitel and set them:

```bash
curl -X PATCH localhost:8000/api/config \
  -H 'Content-Type: application/json' \
  -d '{"human_baseline_aht_sec": 340,
       "agent_cost_per_hour_lkr": 850,
       "baseline_containment_pct": 0,
       "baseline_abandon_pct": 12.0,
       "baseline_csat": 3.4,
       "figures_are_client_supplied": true}'
```

Setting `figures_are_client_supplied: true` removes the placeholder warning
banner. Do not set it until the numbers really are theirs — the banner is what
keeps the claim honest.

---

## Architecture

```
Voice agent  ──POST /ingest/call──►  FastAPI  ──►  Postgres
(or seed_live_call.py)                  │          (calls, alerts, config)
                                        ├── GET /api/*      analytics
                                        └── GET /api/stream SSE live feed
                                                  │
                                        React + Vite + Recharts
```

- **No precomputation.** Every chart is a plain `GROUP BY` over `calls`. At
  ~10k rows each query is single-digit milliseconds; materialised views would
  cost a day and buy nothing.
- **SSE, not WebSocket.** Traffic is one-directional and `EventSource` survives
  corporate proxies that mangle WebSocket upgrades.
- **Ingest is idempotent** on `call_id`, so the agent can retry safely.

### Layout

```
backend/app/
  main.py       FastAPI routes, SSE endpoint
  models.py     Pydantic models — the DATA_CONTRACT.md enums are enforced here
  queries.py    all analytics SQL, one function per endpoint
  alerts.py     emerging-issue detection (spike + incident correlation)
  ingest.py     idempotent upsert
  events.py     in-process pub/sub for SSE
  config.py     runtime-editable ROI inputs
backend/scripts/
  generate_seed.py    ~4 weeks of realistic synthetic data
  seed_live_call.py   single call POSTer — the demo safety net
frontend/src/
  theme.css     design tokens (validated palette — see below)
  api.ts        typed fetch + SSE hook
  panels/       ExecStrip · Operations · Intelligence · LiveFeed
```

---

## How the emerging-issue detector works

For each `(intent, district)` and each topic, it compares the count in the most
recent 2-hour window against the same 2-hour-of-day window on each of the
previous 7 days. It fires when **z ≥ 3 AND count ≥ 5**.

Two design decisions worth knowing, because ops people will probe them:

- **Incident correlation.** One Gampaha outage legitimately trips four
  detectors — `(broadband_fault, Gampaha)` plus the topics `outage`,
  `no_connection`, `fibre` — because they are largely *the same calls*. Firing
  four alarms for one incident reads as noise. Overlapping spikes are measured
  on actual `call_id` sets and folded into a single alert, with the others shown
  as corroborating evidence. One alert saying "three independent signals agree"
  is stronger than four alerts.
- **No absurd percentages.** When the baseline is under 1 call per window, a
  percentage is arithmetically true and rhetorically useless ("up 7743%" reads
  as a broken metric). Below that threshold the alert states raw numbers:
  *"39 in the last 2 hours — normally under 1."*

Alerts auto-resolve once the spike passes, so the panel is never a list of
things that were true at some point.

The detection window anchors to the **newest call in the database**, not
wall-clock now — which is why a stale seed still shows a populated panel, and
why you should regenerate it on demo morning anyway.

---

## Design notes

### Light and dark

Both themes ship. The toggle is in the top bar (☀ / ☾); it defaults to the OS
preference and **persists an explicit choice** in `localStorage`.

> **Demo tip:** click the toggle once on the demo laptop before presenting.
> Dark reads better on a projector, and because the choice is remembered it
> won't be undone by the laptop's OS setting mid-demo.

Dark is a *selected* palette — its own steps from the same hue ramps, validated
against the dark surface — not an automatic inversion of light. Both were
checked with the `dataviz` palette validator (lightness band, chroma floor, CVD
separation, normal-vision floor, contrast):

| | Result |
|---|---|
| dark vs `#16171a` | all checks **PASS** |
| light vs `#fcfcfb` | all **PASS**, contrast **WARN** on `--series-3` (2.74:1) and `--series-4` (2.11:1) |

The light WARN is an obligation, not a shrug. Those two slots are used **only**
on ranked bars that print a visible number beside every bar, which is the
documented relief. If you reuse `--series-3/4` anywhere without a visible label,
re-run the validator and pick another slot. Do not hand-edit a hex in
`theme.css` without re-running it.

Status colours (`--good`, `--warning`, `--serious`, `--critical`) are reserved
for state and never reused as a series colour. In containment-by-intent the
orange bars encode *state* (below the 55% line), not identity. Their base steps
are mode-invariant; only the `-text` variants re-step, because a colour that
works as a 3px bar doesn't necessarily work as 12px type.

**One implementation note worth keeping.** Recharts writes colours as SVG
*presentation attributes*, where `var(--token)` support is inconsistent across
engines — a token that renders correctly in one theme can resolve to nothing in
another and paint black. `useChartTokens()` in `src/theme.ts` reads the computed
values once per theme and hands Recharts real hex. CSS-styled elements keep
using the tokens directly; only the SVG layer needs this. If you add a chart,
pull its colours from `useTokens()`, not from a `var()` string.

Wide content — the heatmap — scrolls inside its own card. The page body never
scrolls horizontally.

---

## Data contract

`DATA_CONTRACT.md` is the interface between the enrichment pipeline and this
dashboard. It is also a demo asset: with a CIO in the room, it answers "what
does this system actually collect" without improvisation.

Note what the dashboard **derives** rather than receives (contract §6):
containment, LKR saved, repeat-caller rate, sentiment delta, alerts. Sending
those pre-computed would create two sources of truth that will disagree on
stage.

---

## Verification

```bash
curl localhost:8000/health                    # call count + newest call
curl localhost:8000/api/kpis   | python3 -m json.tool
curl localhost:8000/api/alerts | python3 -m json.tool   # Gampaha spike present?
cd backend && .venv/bin/python scripts/seed_live_call.py   # live path
```

Not yet verified — **needs a human eye**: layout at projector resolution
(1920×1080), colour legibility from the back of a room, and no horizontal body
scroll. Do this as part of the day-3 dry run.
# ai-call-analytics
