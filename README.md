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

## Running with Docker (recommended)

One command brings up the whole stack — Postgres, the API, and the built
frontend behind nginx:

```bash
docker compose up --build
```

Then open **http://localhost:8080**.

- On a **fresh volume** the backend seeds ~4 weeks of demo data before it starts
  serving, and the web container waits until the API is healthy — so the first
  `up` takes ~30s. Subsequent starts are instant (the seed is skipped when data
  already exists).
- The API is also exposed at **http://localhost:8000** so the demo scripts work
  from the host; nginx proxies `/api` and `/ingest` (SSE included) so the
  dashboard itself only ever talks to port 8080.

Everything is namespaced **`call_agent_analytics_*`** (project, containers,
network, volume) to stay clearly separate from the actual call-agent app's own
Docker resources.

| | |
|---|---|
| Dashboard | http://localhost:8080 |
| API (for scripts) | http://localhost:8000 |
| Postgres (host psql) | localhost:5433 · `callagent` / `callagent` |

**Re-seed with fresh timestamps (do this on demo morning):**

```bash
docker compose exec backend python scripts/generate_seed.py --reset
```

**Run the demo scripts inside the container** (or from the host against :8000):

```bash
docker compose exec backend python scripts/seed_live_call.py --scenario tamil
docker compose exec backend python scripts/seed_live_call.py --scenario  happy
docker compose exec backend python scripts/seed_live_call.py --scenario angry
docker compose exec backend python scripts/trigger_alert.py --district Kandy --intent mobile_coverage
```

**Start clean (wipe the DB volume):** `docker compose down -v && docker compose up --build`

---

## Running without Docker (local dev)

Three terminals. Postgres still runs in a container on **5433**; the backend and
frontend run on the host for fast reloads.

```bash
# 1. Database only
docker compose up -d db

# 2. Backend  (http://localhost:8000)
cd backend
python3 -m venv .venv && .venv/bin/pip install -e .
.venv/bin/python scripts/generate_seed.py --reset      # ~10k calls, ~20s
DATABASE_URL=postgresql://callagent:callagent@localhost:5433/callagent \
  .venv/bin/uvicorn app.main:app --port 8000

# 3. Frontend (http://localhost:5173)
cd frontend
nvm use && npm install && npm run dev
```

Open **http://localhost:5173**. The API is proxied through Vite, so dev also
runs on a single origin with no CORS to negotiate.

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
| 2 | Business impact | CFO | Lead with the **containment rate** and **after-hours coverage** — over half of calls arrive after the centre closes and go unanswered today. Value framed as volume, not an assumed cost rate. |
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
docker-compose.yml   db + backend + web (project: call_agent_analytics)
backend/
  Dockerfile          Python 3.11 image
  entrypoint.sh       wait for db → seed-if-empty → serve uvicorn
frontend/
  Dockerfile          multi-stage: Node build → nginx serve
  nginx.conf          serves the SPA, proxies /api + /ingest (SSE-safe)
backend/app/
  main.py       FastAPI routes, SSE endpoint
  models.py     Pydantic models — the DATA_CONTRACT.md enums are enforced here
  queries.py    all analytics SQL, one function per endpoint
  calls.py      Call History — list rows, per-call detail, derived key points
  alerts.py     emerging-issue detection (spike + incident correlation)
  ingest.py     idempotent upsert
  events.py     in-process pub/sub for SSE
  config.py     read-only operational settings (business hours, timezone)
backend/scripts/
  generate_seed.py    ~4 weeks of realistic synthetic data
  seed_live_call.py   single call POSTer — the demo safety net
  trigger_alert.py    fire an emerging-issue alert for a chosen district
frontend/src/
  theme.css     design tokens (validated palette — see below)
  api.ts        typed fetch + SSE hook
  panels/       ExecStrip · Operations · Intelligence · LiveFeed · CallHistory
```

---

## Call History explorer

A second view (top-bar toggle: **Overview ↔ Call History**) gives ops a
searchable, scrollable list of every call, with a slide-in drawer for the detail
— the per-call transcript-summary that a BA specifically asked for.

- **Columns:** time, customer, service, language, duration, outcome, sentiment,
  CSAT. *Service* is the reason for calling (the intent label), the same
  taxonomy used everywhere else on the dashboard — not a coarse product line.
- **Customer** is a stable reference derived from the hashed MSISDN (`C-04217`),
  so the *same caller always shows the same ref* — repeat callers are visible —
  without ever storing or showing a real number. Display label only; the raw
  MSISDN is never persisted (see `DATA_CONTRACT.md`). This is the answer to the
  CIO's "what customer data does this hold" question: none that identifies a
  person.
- **Filters:** outcome, sentiment, language, service. **Search** matches call ID.
- **Infinite scroll** via an IntersectionObserver sentinel — pages of 50 over
  keyset-free offset pagination; fine at demo scale.
- **The drawer's "Key points" are derived, not stored.** The contract carries no
  `key_points` field; `app/calls.py` reconstructs the bullets from the structured
  fields enrichment already provides — reason for calling, the actions the agent
  took (with ticket refs), the outcome, sentiment movement, retention signals,
  and any unanswered question. So it works on existing data with no pipeline
  change and no migration.

Endpoints: `GET /api/calls` (list, filters, pagination) and
`GET /api/calls/{id}` (drawer detail).

> **Fixed along the way:** `actions_taken` was being double-encoded on ingest
> (manually `json.dumps`-ed *and* run through the connection's jsonb codec),
> so it stored as a jsonb *string* instead of an array. Harmless until something
> read it back — the key-points derivation did. Root-caused in `ingest.store`;
> re-seed picks up the fix. `jsonb_typeof(actions_taken)` should be `array`.

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
containment, repeat-caller rate, sentiment delta, alerts. Sending those
pre-computed would create two sources of truth that will disagree on stage.

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
